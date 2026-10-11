# DetoxChrome Repository

This repository hosts the build configurations and machine learning models for **DetoxChrome** — a modified Chromium build for Android designed to block distractions and promote focused learning.

---

## 🗂 Repository Structure

- **[`chrome/`](./chrome/)**: Contains all necessary build configurations, Dockerfiles, Makefiles, build args (`args.gn`), and custom patch suites to compile DetoxChrome for Android `arm64`.
- **[`finetunedmodel/`](./finetunedmodel/)**: Contains the dataset, training pipeline, fine-tuned checkpoints, ONNX export, and dynamic INT8 quantized model (`export_for_chromium/`) for real-time prompt classification on device.

Refer to the respective README files in each folder for detailed instructions:
- [Chrome Build Guide](./chrome/README.md)
- [Fine-Tuned Model Guide](./finetunedmodel/README.md)
