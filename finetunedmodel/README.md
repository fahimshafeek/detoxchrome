# Student Prompt Classification Model (Fine-Tuned & Quantized)

This directory contains the machine learning assets, training dataset, and deployment pipeline for classifying student prompts between **Conceptual Learning** (`0`) and **Homework Cheating** (`1`).

---

## 📊 Performance Metrics

- **Base Architecture**: `sentence-transformers/all-MiniLM-L6-v2`
- **Fine-Tuning Strategy**: 4 Epochs, AdamW (lr=3e-5, weight_decay=0.01), Stratified 85/15 Split
- **Validation Precision**: **100.00%**
- **Validation Recall**: **100.00%**
- **Validation F1 / F0.5**: **100.00%**
- **False Positive Rate**: **0.00%** (0 false positives on test validation set)
- **Quantization**: Dynamic INT8 quantization optimized for ARM64 CPU
- **Quantized Package Size**: **22.96 MB** (`model_quantized.onnx` + tokenizers)
- **Average CPU Inference Latency**: **~5.5 ms** per prompt

---

## 📁 Directory Structure

```
finetunedmodel/
├── dataset.jsonl           # 2,000 labeled prompt examples (1,000 conceptual, 1,000 cheating)
├── pipeline.py             # End-to-end training, ONNX export, INT8 quantization & benchmark script
├── All_MiniLM_L6_v2.ipynb  # Jupyter notebook equivalent
├── requirements.txt        # Frozen dependencies
├── decrease_ai/            # AI reduction package with HTML UI test & ONNX model
├── export_for_chromium/    # Production-ready package for Chromium Android integration
│   ├── model_quantized.onnx  # 22 MB INT8 quantized ONNX model
│   ├── tokenizer.json        # Fast tokenizer definition
│   └── vocab.txt             # BERT vocabulary file
├── best_checkpoint/        # Best PyTorch fine-tuned model checkpoint
├── onnx_model/             # Unquantized FP32 ONNX model export
├── quantized_model/        # Intermediate INT8 quantization files
└── training_output/        # Training logs and epoch checkpoint states
```

---

## 🚀 Reproduction & Inference

### Setup Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run Full Pipeline
```bash
python pipeline.py
```

### Run Quantized ONNX Inference
```python
import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("./export_for_chromium")
session = ort.InferenceSession("./export_for_chromium/model_quantized.onnx", providers=["CPUExecutionProvider"])

prompt = "Can you explain the intuition behind the Heisenberg uncertainty principle?"
inputs = tokenizer(prompt, max_length=128, padding="max_length", truncation=True, return_tensors="np")
ort_inputs = {
    "input_ids": inputs["input_ids"].astype(np.int64),
    "attention_mask": inputs["attention_mask"].astype(np.int64)
}
outputs = session.run(None, ort_inputs)
probs = np.exp(outputs[0][0]) / np.sum(np.exp(outputs[0][0]))
print("Conceptual (0):", probs[0], "Cheating (1):", probs[1])
```
