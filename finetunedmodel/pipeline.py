#!/usr/bin/env python3
"""
Full Autonomous ML Pipeline for Student Prompt Classification:
1. Stratified 85/15 train-val split from dataset.jsonl (seed 42)
2. Fine-tune sentence-transformers/all-MiniLM-L6-v2:
   - max_length=128, padding='max_length', truncation=True
   - 4 epochs, lr=3e-5, batch_size=16, weight_decay=0.01
   - Evaluate F1, Precision, Recall, Confusion Matrix at each epoch
   - Prioritize minimizing False Positives (label 0 misclassified as 1)
   - Save best checkpoint locally to ./best_checkpoint
3. Quantize and Export to ONNX via Hugging Face Optimum:
   - Export best checkpoint to ONNX
   - Dynamic INT8 quantization optimized for ARM64 CPU
   - Copy only production-ready assets to ./export_for_chromium:
     - model_quantized.onnx
     - vocab.txt
     - tokenizer.json
4. Verification & Benchmarking:
   - Load ./export_for_chromium/model_quantized.onnx with ONNX Runtime
   - Run inference on 5 test strings (class 0 and class 1)
   - Measure & report average CPU inference latency per prompt in ms
   - Verify file sizes in ./export_for_chromium/
"""

import os
import sys
import json
import time
import shutil
import numpy as np
import torch
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix, classification_report
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    Trainer,
    TrainingArguments,
    TrainerCallback,
    set_seed
)
from optimum.onnxruntime import ORTModelForSequenceClassification, ORTQuantizer
from optimum.onnxruntime.configuration import AutoQuantizationConfig
import onnxruntime as ort

def set_all_seeds(seed=42):
    set_seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

class PromptDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels):
        self.encodings = encodings
        self.labels = labels

    def __getitem__(self, idx):
        item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.long)
        return item

    def __len__(self):
        return len(self.labels)

def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    
    # Binary classification metrics where positive class = 1 (homework dumping / cheating)
    # Minimizing False Positives (label 0 misclassified as label 1) directly maximizes Precision!
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, preds, average='binary', zero_division=0
    )
    
    cm = confusion_matrix(labels, preds, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    
    # False Positive Rate = FP / (FP + TN)
    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    
    # F0.5 score weights precision twice as much as recall:
    # F_beta = (1 + beta^2) * (P * R) / (beta^2 * P + R)
    beta = 0.5
    beta_sq = beta ** 2
    f0_5 = (1 + beta_sq) * (precision * recall) / (beta_sq * precision + recall) if (precision + recall) > 0 else 0.0

    # Composite score prioritizing minimizing False Positives:
    # 70% precision, 30% f1, penalizing any FP
    score_min_fp = float(0.7 * precision + 0.3 * f1 - 0.1 * fpr)

    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "f0_5": float(f0_5),
        "false_positives": int(fp),
        "false_positive_rate": fpr,
        "true_positives": int(tp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "score_min_fp": score_min_fp
    }

class DetailedEvalCallback(TrainerCallback):
    """Logs detailed metrics and confusion matrix at each evaluation."""
    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        if metrics:
            epoch = metrics.get("epoch", "N/A")
            prec = metrics.get("eval_precision", 0.0)
            rec = metrics.get("eval_recall", 0.0)
            f1 = metrics.get("eval_f1", 0.0)
            f0_5 = metrics.get("eval_f0_5", 0.0)
            fp = metrics.get("eval_false_positives", 0)
            tp = metrics.get("eval_true_positives", 0)
            tn = metrics.get("eval_true_negatives", 0)
            fn = metrics.get("eval_false_negatives", 0)
            fpr = metrics.get("eval_false_positive_rate", 0.0)
            
            print("\n" + "=" * 70)
            print(f"📊 EVALUATION SUMMARY (Epoch {epoch})")
            print("=" * 70)
            print(f"  • Precision (Class 1):       {prec * 100:.2f}%")
            print(f"  • Recall (Class 1):          {rec * 100:.2f}%")
            print(f"  • F1 Score:                  {f1 * 100:.2f}%")
            print(f"  • F0.5 Score (FP Penalized): {f0_5 * 100:.2f}%")
            print(f"  • False Positives (0 as 1):  {fp} / {tn + fp} (FPR: {fpr * 100:.2f}%)")
            print(f"  • Confusion Matrix:")
            print(f"      [TN (0 as 0): {tn:3d} | FP (0 as 1): {fp:3d}]")
            print(f"      [FN (1 as 0): {fn:3d} | TP (1 as 1): {tp:3d}]")
            print("=" * 70 + "\n")

def run_pipeline():
    print("=" * 70)
    print("🚀 STARTING AUTONOMOUS ML PIPELINE")
    print("=" * 70)
    
    set_all_seeds(42)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Execution device for training: {device.upper()}")
    
    # -------------------------------------------------------------------------
    # STEP 1: Load and Split Dataset
    # -------------------------------------------------------------------------
    dataset_path = "dataset.jsonl"
    print(f"\n[1/4] Loading dataset from '{dataset_path}'...")
    texts = []
    labels = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            texts.append(item["text"])
            labels.append(int(item["label"]))
            
    print(f"Total samples loaded: {len(texts)}")
    print(f"Class 0 (Conceptual): {labels.count(0)} | Class 1 (Cheating): {labels.count(1)}")
    
    # Stratified 85% train / 15% validation split (seed 42)
    train_texts, val_texts, train_labels, val_labels = train_test_split(
        texts,
        labels,
        test_size=0.15,
        random_state=42,
        stratify=labels
    )
    print(f"Stratified split completed:")
    print(f"  Train set: {len(train_texts)} samples (Class 0: {train_labels.count(0)}, Class 1: {train_labels.count(1)})")
    print(f"  Validation set: {len(val_texts)} samples (Class 0: {val_labels.count(0)}, Class 1: {val_labels.count(1)})")
    
    # -------------------------------------------------------------------------
    # STEP 2: Tokenization and Fine-Tuning
    # -------------------------------------------------------------------------
    base_model_name = "sentence-transformers/all-MiniLM-L6-v2"
    print(f"\n[2/4] Loading tokenizer and model: {base_model_name}")
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    
    print("Tokenizing train and validation sets (max_length=128, padding='max_length', truncation=True)...")
    train_encodings = tokenizer(
        train_texts,
        max_length=128,
        padding="max_length",
        truncation=True
    )
    val_encodings = tokenizer(
        val_texts,
        max_length=128,
        padding="max_length",
        truncation=True
    )
    
    train_dataset = PromptDataset(train_encodings, train_labels)
    val_dataset = PromptDataset(val_encodings, val_labels)
    
    id2label = {0: "CONCEPTUAL_LEARNING", 1: "HOMEWORK_CHEATING"}
    label2id = {"CONCEPTUAL_LEARNING": 0, "HOMEWORK_CHEATING": 1}
    
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model_name,
        num_labels=2,
        id2label=id2label,
        label2id=label2id
    )
    
    output_dir = "./training_output"
    best_checkpoint_dir = "./best_checkpoint"
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=4,
        learning_rate=3e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="score_min_fp",  # Prioritizes minimizing False Positives (high precision)
        greater_is_better=True,
        seed=42,
        report_to="none",
        use_cpu=(device == "cpu")
    )
    
    if os.path.exists(os.path.join(best_checkpoint_dir, "model.safetensors")):
        print(f"Found existing fine-tuned best checkpoint in '{best_checkpoint_dir}'.")
        model = AutoModelForSequenceClassification.from_pretrained(best_checkpoint_dir)
        trainer = Trainer(
            model=model,
            args=training_args,
            eval_dataset=val_dataset,
            processing_class=tokenizer,
            compute_metrics=compute_metrics,
            callbacks=[DetailedEvalCallback()]
        )
        print("\nEvaluating existing best checkpoint on validation set:")
        final_eval = trainer.evaluate()
        print(f"Validation Metrics: {json.dumps({k: round(v, 4) for k, v in final_eval.items() if isinstance(v, (int, float))}, indent=2)}")
    else:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            processing_class=tokenizer,
            compute_metrics=compute_metrics,
            callbacks=[DetailedEvalCallback()]
        )
        
        print("\nStarting model fine-tuning (4 epochs)...")
        train_result = trainer.train()
        
        print("\nFinal evaluation on validation set with best checkpoint:")
        final_eval = trainer.evaluate()
        print(f"Final Validation Metrics: {json.dumps({k: round(v, 4) for k, v in final_eval.items() if isinstance(v, (int, float))}, indent=2)}")
        
        print(f"\nSaving best checkpoint to '{best_checkpoint_dir}'...")
        trainer.save_model(best_checkpoint_dir)
        tokenizer.save_pretrained(best_checkpoint_dir)
        print("Checkpoint and tokenizer saved successfully.")
    
    # -------------------------------------------------------------------------
    # STEP 3: Quantize and Export to ONNX
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("[3/4] QUANTIZATION & ONNX EXPORT")
    print("=" * 70)
    
    intermediate_onnx_dir = "./onnx_model"
    intermediate_quant_dir = "./quantized_model"
    export_for_chromium_dir = "./export_for_chromium"
    
    for d in [intermediate_onnx_dir, intermediate_quant_dir, export_for_chromium_dir]:
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d, exist_ok=True)
        
    print(f"Exporting model from '{best_checkpoint_dir}' to ONNX format using Optimum...")
    ort_model = ORTModelForSequenceClassification.from_pretrained(
        best_checkpoint_dir,
        export=True
    )
    ort_model.save_pretrained(intermediate_onnx_dir)
    print(f"ONNX model saved to '{intermediate_onnx_dir}'.")
    
    print("\nApplying Dynamic INT8 Quantization optimized for ARM64 CPU...")
    quantizer = ORTQuantizer.from_pretrained(intermediate_onnx_dir)
    # AutoQuantizationConfig.arm64(is_static=False, per_channel=True) generates optimal dynamic INT8 quantization config for ARM64
    dqconfig = AutoQuantizationConfig.arm64(is_static=False, per_channel=True)
    quantizer.quantize(save_dir=intermediate_quant_dir, quantization_config=dqconfig)
    print(f"Quantization complete. Files in '{intermediate_quant_dir}': {os.listdir(intermediate_quant_dir)}")
    
    # Production packaging for Chromium:
    # Target files:
    #   - model_quantized.onnx
    #   - vocab.txt
    #   - tokenizer.json
    print(f"\nPackaging ONLY production-ready assets to '{export_for_chromium_dir}'...")
    
    # Locate quantized onnx model file
    quantized_onnx_source = None
    for fname in os.listdir(intermediate_quant_dir):
        if fname.endswith(".onnx"):
            quantized_onnx_source = os.path.join(intermediate_quant_dir, fname)
            break
            
    if not quantized_onnx_source:
        raise FileNotFoundError(f"Could not find quantized .onnx model in {intermediate_quant_dir}")
        
    target_onnx = os.path.join(export_for_chromium_dir, "model_quantized.onnx")
    shutil.copy2(quantized_onnx_source, target_onnx)
    print(f"  ✓ Copied {quantized_onnx_source} -> {target_onnx}")
    
    # Locate vocab.txt and tokenizer.json
    vocab_source = os.path.join(best_checkpoint_dir, "vocab.txt")
    if not os.path.exists(vocab_source):
        # Fallback to tokenizer if saved elsewhere
        vocab_source = tokenizer.vocab_file if hasattr(tokenizer, "vocab_file") else None
    target_vocab = os.path.join(export_for_chromium_dir, "vocab.txt")
    shutil.copy2(vocab_source, target_vocab)
    print(f"  ✓ Copied {vocab_source} -> {target_vocab}")
    
    tok_json_source = os.path.join(best_checkpoint_dir, "tokenizer.json")
    target_tok_json = os.path.join(export_for_chromium_dir, "tokenizer.json")
    shutil.copy2(tok_json_source, target_tok_json)
    print(f"  ✓ Copied {tok_json_source} -> {target_tok_json}")
    
    # Verify ONLY the 3 requested files are in export_for_chromium_dir
    packaged_files = sorted(os.listdir(export_for_chromium_dir))
    expected_files = sorted(["model_quantized.onnx", "vocab.txt", "tokenizer.json"])
    assert packaged_files == expected_files, f"Expected {expected_files}, got {packaged_files}"
    print(f"\nVerification: './export_for_chromium/' contains exactly: {packaged_files}")
    
    # -------------------------------------------------------------------------
    # STEP 4: Verification & Benchmarking
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("[4/4] VERIFICATION & CPU BENCHMARKING")
    print("=" * 70)
    
    print(f"Loading '{target_onnx}' with ONNX Runtime CPU InferenceSession...")
    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = 4
    sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(target_onnx, sess_options, providers=["CPUExecutionProvider"])
    
    test_prompts = [
        # Class 0: Conceptual learning
        {"text": "Can you explain the intuition behind the Heisenberg uncertainty principle?", "expected": 0, "desc": "Conceptual: Quantum Physics"},
        {"text": "What is the key difference between BFS and DFS in graph traversal?", "expected": 0, "desc": "Conceptual: Algorithms"},
        {"text": "Why does demand curve slope downwards according to microeconomic theory?", "expected": 0, "desc": "Conceptual: Economics"},
        # Class 1: Direct homework dumping / cheating
        {"text": "Do exercise 4.2 for me, find all values of x in 3x^2 - 12x + 9 = 0 with full solutions.", "expected": 1, "desc": "Cheating: Homework Problem"},
        {"text": "Write my complete lab report on pendulum motion including abstract, method, and results.", "expected": 1, "desc": "Cheating: Lab Report Dump"},
    ]
    
    print("\nRunning inference on 5 test strings:")
    print("-" * 70)
    
    for i, test_case in enumerate(test_prompts, 1):
        prompt = test_case["text"]
        expected_class = test_case["expected"]
        desc = test_case["desc"]
        
        # Tokenize with max_length=128
        inputs = tokenizer(
            prompt,
            max_length=128,
            padding="max_length",
            truncation=True,
            return_tensors="np"
        )
        
        # Prepare inputs for ONNX
        ort_inputs = {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64)
        }
        if "token_type_ids" in inputs and "token_type_ids" in [node.name for node in session.get_inputs()]:
            ort_inputs["token_type_ids"] = inputs["token_type_ids"].astype(np.int64)
            
        outputs = session.run(None, ort_inputs)
        logits = outputs[0][0]
        
        # Softmax probabilities
        exp_logits = np.exp(logits - np.max(logits))
        probs = exp_logits / np.sum(exp_logits)
        pred_class = int(np.argmax(logits))
        pred_label_str = id2label[pred_class]
        expected_label_str = id2label[expected_class]
        
        status = "✅ PASS" if pred_class == expected_class else "❌ FAIL"
        print(f"[{i}] {status} | Expected: {expected_label_str} | Pred: {pred_label_str}")
        print(f"    Prompt: \"{prompt}\"")
        print(f"    Probabilities: Conceptual (0)={probs[0]:.4f}, Cheating (1)={probs[1]:.4f}")
        print("-" * 70)
        
    # Latency benchmarking
    print("\nBenchmarking CPU inference latency per prompt...")
    # Warm-up (10 runs)
    dummy_input = tokenizer(
        "Explain the intuition behind gradient descent optimization.",
        max_length=128,
        padding="max_length",
        truncation=True,
        return_tensors="np"
    )
    ort_dummy = {
        "input_ids": dummy_input["input_ids"].astype(np.int64),
        "attention_mask": dummy_input["attention_mask"].astype(np.int64)
    }
    if "token_type_ids" in dummy_input and "token_type_ids" in [node.name for node in session.get_inputs()]:
        ort_dummy["token_type_ids"] = dummy_input["token_type_ids"].astype(np.int64)
        
    for _ in range(15):
        session.run(None, ort_dummy)
        
    # Timed runs over 100 iterations
    num_runs = 100
    latencies = []
    for _ in range(num_runs):
        for tc in test_prompts:
            inp = tokenizer(
                tc["text"],
                max_length=128,
                padding="max_length",
                truncation=True,
                return_tensors="np"
            )
            ort_inp = {
                "input_ids": inp["input_ids"].astype(np.int64),
                "attention_mask": inp["attention_mask"].astype(np.int64)
            }
            if "token_type_ids" in inp and "token_type_ids" in [node.name for node in session.get_inputs()]:
                ort_inp["token_type_ids"] = inp["token_type_ids"].astype(np.int64)
                
            t0 = time.perf_counter()
            session.run(None, ort_inp)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0) # in ms
            
    avg_latency = np.mean(latencies)
    p50_latency = np.median(latencies)
    p95_latency = np.percentile(latencies, 95)
    p99_latency = np.percentile(latencies, 99)
    min_latency = np.min(latencies)
    
    print(f"CPU Inference Benchmark ({len(latencies)} inferences measured):")
    print(f"  • Average Latency: {avg_latency:.2f} ms")
    print(f"  • Median (p50):    {p50_latency:.2f} ms")
    print(f"  • 95th Percentile: {p95_latency:.2f} ms")
    print(f"  • 99th Percentile: {p99_latency:.2f} ms")
    print(f"  • Min Latency:     {min_latency:.2f} ms")
    
    # File sizes check
    print("\n" + "=" * 70)
    print("📦 PRODUCTION ASSETS READY FOR CHROMIUM DEPLOYMENT")
    print("=" * 70)
    total_size = 0
    for f in sorted(os.listdir(export_for_chromium_dir)):
        fpath = os.path.join(export_for_chromium_dir, f)
        fsize = os.path.getsize(fpath)
        total_size += fsize
        if fsize >= 1024 * 1024:
            fsize_str = f"{fsize / (1024 * 1024):.2f} MB"
        else:
            fsize_str = f"{fsize / 1024:.2f} KB"
        print(f"  • {f:<22} : {fsize_str} ({fsize:,} bytes)")
        
    print(f"Total package size: {total_size / (1024 * 1024):.2f} MB")
    print("=" * 70)
    print("✅ PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_pipeline()
