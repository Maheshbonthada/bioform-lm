# Model Checkpoints Guide

## 📍 Where Are My Model Weights?

Your trained model weights are automatically saved in:

```
experiments/checkpoints/
```

Each training run creates a new checkpoint file named:
```
checkpoint_epoch_N.pt
```

where `N` is the epoch number.

## 📊 Current Checkpoints

Run this to see what checkpoints exist:

```bash
# Simple list
make checkpoints

# Detailed list with epoch/validation loss
make checkpoints-verbose

# Or directly:
python scripts/list_checkpoints.py --verbose
```

Each checkpoint file contains ~55-58 MB and includes:
- Model state dict (the actual trained weights)
- Optimizer state dict (for resuming training)
- Epoch number
- Validation loss at that epoch

## 🚀 How to Use Checkpoints

### Option 1: Load for Inference

```python
import torch
from model.tokenizer import FormulationTokenizer
from experiments.train import BioFormLM

# Load the best checkpoint
checkpoint = torch.load(
    "experiments/checkpoints/checkpoint_epoch_33.pt", 
    map_location="cpu"  # or "cuda"
)

# Create a model with the same architecture
model = BioFormLM(
    vocab_size=199,           # From tokenizer
    hidden_dim=256,           # From config
    num_layers=6,             # From config
    num_heads=8,              # From config
    feedforward_dim=1024,     # From config
    max_seq_len=64,           # From config
    dropout=0.1               # From config
)

# Load the trained weights
model.load_state_dict(checkpoint["model_state_dict"])

# Set to evaluation mode
model.eval()

# Now use for inference
with torch.no_grad():
    # Your inference code here
    stability_logits, recipe_logits = model(input_ids)
```

### Option 2: Resume Training from a Checkpoint

```python
import torch
from model.tokenizer import FormulationTokenizer
from experiments.train import BioFormLM, Trainer

# Load checkpoint
checkpoint = torch.load("experiments/checkpoints/checkpoint_epoch_33.pt")

# Recreate model and trainer
model = BioFormLM(...)  # Same architecture as before
trainer = Trainer(model, train_loader, val_loader, device="cuda")

# Load the saved state
model.load_state_dict(checkpoint["model_state_dict"])
trainer.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
start_epoch = checkpoint["epoch"] + 1

# Continue training from epoch 34
trainer.train(epochs=50)  # Will train epochs 34-50
```

### Option 3: Use in the Evaluation Pipeline

```python
from scripts.evaluate import main as evaluate

# Evaluate on real data (BioFormBench)
evaluate(
    checkpoint_path="experiments/checkpoints/checkpoint_epoch_33.pt",
    data_file="data/bioformbench.csv",
    protocol="lopo",
    output_dir="evaluation/results"
)
```

## 📝 Checkpoint File Format

Each `.pt` file is a PyTorch checkpoint dictionary:

```python
{
    "epoch": 33,                           # Training epoch
    "model_state_dict": {...},             # Model weights
    "optimizer_state_dict": {...},         # Optimizer state (momentum, etc.)
    "val_loss": 0.8234,                    # Best validation loss
}
```

You can inspect a checkpoint:

```python
import torch

ckpt = torch.load("experiments/checkpoints/checkpoint_epoch_33.pt")
print(f"Epoch: {ckpt['epoch']}")
print(f"Val Loss: {ckpt['val_loss']:.4f}")
print(f"Model keys: {ckpt['model_state_dict'].keys()}")
```

## 🎯 Which Checkpoint to Use?

- **Best validation loss:** `checkpoint_epoch_33.pt` (as shown in the saved files)
  - This is automatically selected during training (lowest val loss)
  - Recommended for inference and evaluation
  
- **Latest checkpoint:** The one with the highest epoch number
  - Might still be training, not necessarily the best

- **For ablation studies:**
  - Use the same checkpoint for all baselines to ensure fair comparison
  - Recommended: the best checkpoint (epoch 33)

## 🔄 Automatic Checkpoint Management

The training script automatically:
1. **Saves checkpoints only when validation loss improves** (no need to save all epochs)
2. **Keeps all improving checkpoints** (so you can try different ones)
3. **Logs checkpoint location to console and `experiments/train.log`**
4. **Records epoch and val_loss for reference**

Early stopping kicks in after 15 epochs with no improvement (patience counter).

## 📂 Directory Structure

```
experiments/
├── train.py                  # Training script
├── train.log                 # Training logs
└── checkpoints/
    ├── checkpoint_epoch_1.pt
    ├── checkpoint_epoch_3.pt
    ├── checkpoint_epoch_5.pt
    ... (all saved checkpoints)
    └── checkpoint_epoch_33.pt  # Best (lowest val loss)
```

## 🐛 Troubleshooting

**Q: I can't find any checkpoints**
- A: Check that training actually ran to completion
  - Look at `experiments/train.log` for training output
  - Run `make train` to ensure training completes
  - Checkpoints only save after the first epoch

**Q: Checkpoint file is corrupted**
- A: Try loading it to check:
  ```python
  import torch
  try:
      ckpt = torch.load("path/to/checkpoint.pt")
      print("✓ Checkpoint is valid")
  except Exception as e:
      print(f"✗ Checkpoint error: {e}")
  ```

**Q: What if I want to keep multiple training runs?**
- A: Create a new output directory:
  ```bash
  python scripts/train.py \
    --phase synthetic \
    --num_samples 100000 \
    --output_dir experiments/checkpoints_v2
  ```
  Then list them with `ls experiments/checkpoints_v2/`

**Q: How do I use a checkpoint for the critic module?**
- A: The critic is a separate module, it has its own checkpoints:
  ```python
  from model.critic import FormulationCritic
  
  critic = FormulationCritic(...)
  critic.load_state_dict(
      torch.load("experiments/checkpoints_critic/best.pt")["model_state_dict"]
  )
  ```

## 📚 Related Commands

```bash
# List all checkpoints
make checkpoints

# Show checkpoint details
make checkpoints-verbose

# Generate new training data
make data-large

# Train a new model (creates new checkpoints)
make train-full

# Evaluate using best checkpoint
python scripts/evaluate.py \
  --checkpoint experiments/checkpoints/checkpoint_epoch_33.pt \
  --data_file data/bioformbench.csv \
  --protocol lopo
```

## ✅ Summary

- ✅ Model weights automatically saved in `experiments/checkpoints/`
- ✅ Each checkpoint ~55-58 MB (complete model + optimizer state)
- ✅ Best checkpoint: `checkpoint_epoch_33.pt` (lowest validation loss)
- ✅ Use `make checkpoints` to list what's available
- ✅ Load with `torch.load()` for inference or resuming training

Your trained model is ready to use! 🚀
