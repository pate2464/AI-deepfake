"""Test moondream2 loading with direct GPU weight loading."""
import torch, gc
import transformers
from safetensors.torch import load_file
import glob, os

gc.collect()
torch.cuda.empty_cache()

# Monkey-patch for moondream2 compat with transformers 5.4
_orig_getattr = transformers.PreTrainedModel.__getattr__
def _patched_getattr(self, name):
    if name == 'all_tied_weights_keys':
        return {}
    return _orig_getattr(self, name)
transformers.PreTrainedModel.__getattr__ = _patched_getattr

# Step 1: Load config
print("Loading config...")
config = transformers.AutoConfig.from_pretrained('vikhyatk/moondream2', trust_remote_code=True)

# Step 2: Create empty model
print("Creating empty model...")
from accelerate import init_empty_weights
with init_empty_weights():
    model = transformers.AutoModelForCausalLM.from_config(config, trust_remote_code=True)
print(f"Model type: {type(model)}")

# Step 3: Load weights directly to GPU (bypasses Windows pagefile mmap)
cache_dir = os.path.expanduser('~/.cache/huggingface/hub/models--vikhyatk--moondream2')
sf_files = glob.glob(os.path.join(cache_dir, 'snapshots/*/model.safetensors'))
if not sf_files:
    print("ERROR: No safetensors file found!")
    exit(1)
sf_path = sf_files[0]
print(f"Loading {os.path.getsize(sf_path)/1024**3:.2f}GB to GPU...")

try:
    state_dict = load_file(sf_path, device='cuda')
    print(f"Loaded {len(state_dict)} tensors to GPU")
    
    model.load_state_dict(state_dict, strict=False, assign=True)
    model = model.to(device='cuda', dtype=torch.bfloat16)
    model.eval()
    del state_dict
    gc.collect()
    torch.cuda.empty_cache()
    
    print("SUCCESS!")
    print(f"GPU mem: {torch.cuda.memory_allocated()/(1024**3):.2f} GB")
    print(f"encode_image: {hasattr(model, 'encode_image')}")
    print(f"answer_question: {hasattr(model, 'answer_question')}")
    
    # Quick test
    if hasattr(model, 'encode_image') and hasattr(model, 'answer_question'):
        from PIL import Image
        tokenizer = transformers.AutoTokenizer.from_pretrained('vikhyatk/moondream2', trust_remote_code=True)
        
        # Test with the AI-generated pizza image
        img_path = r"C:\Users\g18g1\Downloads\Gemini_Generated_Image_6qre9r6qre9r6qre (1).png"
        if os.path.exists(img_path):
            img = Image.open(img_path).convert("RGB")
            if max(img.size) > 768:
                ratio = 768 / max(img.size)
                img = img.resize((int(img.size[0]*ratio), int(img.size[1]*ratio)), Image.LANCZOS)
            print(f"Image size: {img.size}")
            enc = model.encode_image(img)
            
            prompt = ("You are an expert forensic image analyst. Analyze this image carefully for signs of AI generation. "
                     "Look for: unnatural textures, impossible physics, garbled text, inconsistent lighting, "
                     "repeating patterns, uncanny faces/hands, background inconsistencies. "
                     "Is this image AI-generated? Explain why or why not in detail.")
            answer = model.answer_question(enc, prompt, tokenizer)
            print(f"\nVLM Analysis:\n{answer}")
        else:
            img = Image.new('RGB', (224, 224), (128, 64, 32))
            enc = model.encode_image(img)
            answer = model.answer_question(enc, "What do you see?", tokenizer)
            print(f"Test answer: {answer}")
    else:
        print("Methods:", [m for m in dir(model) if not m.startswith('_') and callable(getattr(model, m))])
        
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
