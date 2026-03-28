"""Debug script — analyzes an image through each detection layer independently
and prints detailed diagnostics. Usage:

    python debug_image.py <image_path>
"""

import sys
import os
import json

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

# Register HEIC opener before anything else
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    print("[OK] pillow-heif registered — HEIC/HEIF support enabled")
except ImportError:
    print("[WARN] pillow-heif not installed — HEIC files will fail")

import numpy as np
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def debug_open(image_path):
    """Try to open the image and print basic info."""
    section("IMAGE OPEN TEST")
    try:
        img = Image.open(image_path)
        print(f"  Format:   {img.format}")
        print(f"  Mode:     {img.mode}")
        print(f"  Size:     {img.size[0]}x{img.size[1]}")
        print(f"  Info keys: {list(img.info.keys())}")
        
        # Try converting to RGB
        rgb = img.convert("RGB")
        arr = np.array(rgb)
        print(f"  RGB array shape: {arr.shape}, dtype: {arr.dtype}")
        print(f"  Pixel range: [{arr.min()}, {arr.max()}]")
        print(f"  Mean pixel value: {arr.mean():.1f}")
        print("[OK] Image opened successfully")
        return img
    except Exception as e:
        print(f"[FAIL] Cannot open image: {e}")
        return None


def debug_exif(img, image_path):
    """Debug EXIF extraction."""
    section("LAYER 1: EXIF METADATA")
    
    # Check format
    ext = os.path.splitext(image_path)[1].lower()
    print(f"  File extension: {ext}")
    
    # Try Pillow EXIF
    raw_exif = img.getexif()
    print(f"  Pillow getexif() entries: {len(raw_exif)}")
    
    if raw_exif:
        for tag_id, value in raw_exif.items():
            tag_name = TAGS.get(tag_id, f"Unknown({tag_id})")
            val_str = str(value)[:100]
            print(f"    {tag_name:30s} = {val_str}")
    else:
        print("  [WARN] No EXIF data from Pillow")
    
    # Try exifread library
    try:
        import exifread
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=False)
        print(f"\n  exifread tags: {len(tags)}")
        for k, v in sorted(tags.items()):
            print(f"    {k:40s} = {str(v)[:80]}")
    except ImportError:
        print("  [SKIP] exifread not installed")
    except Exception as e:
        print(f"  [WARN] exifread failed: {e}")
    
    # Check for HEIC-specific metadata in img.info
    if "exif" in img.info:
        print(f"\n  Raw EXIF bytes present in img.info: {len(img.info['exif'])} bytes")
    
    # Try to get IFD data (deeper EXIF)
    try:
        from PIL.ExifTags import IFD
        exif_data = img.getexif()
        for ifd_key in [IFD.Exif, IFD.GPSInfo, IFD.Interop]:
            ifd = exif_data.get_ifd(ifd_key)
            if ifd:
                print(f"\n  IFD {ifd_key} ({len(ifd)} entries):")
                for tag_id, value in ifd.items():
                    tag_name = TAGS.get(tag_id, GPSTAGS.get(tag_id, f"Unknown({tag_id})"))
                    print(f"    {tag_name:30s} = {str(value)[:80]}")
    except Exception as e:
        print(f"  [WARN] IFD enumeration failed: {e}")


def debug_ela(img, image_path):
    """Debug ELA analysis."""
    section("LAYER 2: ERROR LEVEL ANALYSIS")
    
    import io
    
    quality = 90
    scale = 15
    
    img_rgb = img.convert("RGB")
    
    # Re-save as JPEG
    buf = io.BytesIO()
    img_rgb.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")
    
    original_arr = np.array(img_rgb, dtype=np.float64)
    resaved_arr = np.array(resaved, dtype=np.float64)
    diff = np.abs(original_arr - resaved_arr)
    
    flat = diff.mean(axis=2)
    
    mean_err = float(np.mean(flat))
    std_dev = float(np.std(flat))
    median_err = float(np.median(flat))
    max_err = float(np.max(flat))
    uniformity = std_dev / (mean_err + 1e-8)
    
    print(f"  Quality used:  {quality}")
    print(f"  Image size:    {img_rgb.size}")
    print(f"  Mean error:    {mean_err:.4f}")
    print(f"  Std dev:       {std_dev:.4f}")
    print(f"  Median error:  {median_err:.4f}")
    print(f"  Max error:     {max_err:.4f}")
    print(f"  Uniformity:    {uniformity:.4f}  (std_dev / mean)")
    
    # Current thresholds
    print(f"\n  --- Current scoring logic ---")
    if std_dev < 2.0 and mean_err < 3.0:
        print(f"  MATCHED: std_dev({std_dev:.2f}) < 2.0 AND mean({mean_err:.2f}) < 3.0")
        print(f"  -> Score = 0.9  (EXTREMELY UNIFORM — flagged as AI)")
        print(f"  [PROBLEM] This is likely a false positive for HEIC/compressed photos!")
    elif uniformity < 0.5:
        print(f"  MATCHED: uniformity({uniformity:.4f}) < 0.5")
        print(f"  -> Score = 0.7")
    elif uniformity < 1.0:
        print(f"  MATCHED: uniformity({uniformity:.4f}) < 1.0")
        print(f"  -> Score = 0.5")
    else:
        print(f"  MATCHED: uniformity({uniformity:.4f}) >= 1.0")
        print(f"  -> Score = 0.2  (real photo pattern)")
    
    # Percentile analysis
    p5 = np.percentile(flat, 5)
    p25 = np.percentile(flat, 25)
    p75 = np.percentile(flat, 75)
    p95 = np.percentile(flat, 95)
    print(f"\n  Error percentiles: p5={p5:.2f} p25={p25:.2f} median={median_err:.2f} p75={p75:.2f} p95={p95:.2f}")
    
    # Was the original already JPEG-compressed?
    is_jpeg = image_path.lower().endswith((".jpg", ".jpeg"))
    is_heic = image_path.lower().endswith((".heic", ".heif"))
    print(f"\n  Is JPEG:  {is_jpeg}")
    print(f"  Is HEIC:  {is_heic}")
    if is_heic:
        print("  [NOTE] HEIC uses HEVC (H.265) compression — NOT JPEG.")
        print("         When re-saved as JPEG, the diff captures the codec")
        print("         difference, NOT manipulation. ELA was designed for JPEG->JPEG.")
        print("         Need to account for this in scoring!")


def debug_fft(img):
    """Debug FFT analysis."""
    section("LAYER 4: FFT FREQUENCY ANALYSIS")
    
    gray = np.array(img.convert("L"), dtype=np.float64)
    
    f_transform = np.fft.fft2(gray)
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.abs(f_shift)
    
    h, w = gray.shape
    cy, cx = h // 2, w // 2
    
    radius_low = min(h, w) // 8
    radius_mid = min(h, w) // 4
    
    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    
    mask_low = dist <= radius_low
    mask_mid = (dist > radius_low) & (dist <= radius_mid)
    mask_high = dist > radius_mid
    
    total_energy = np.sum(magnitude ** 2)
    low_energy = np.sum(magnitude[mask_low] ** 2) / (total_energy + 1e-10)
    mid_energy = np.sum(magnitude[mask_mid] ** 2) / (total_energy + 1e-10)
    high_energy = np.sum(magnitude[mask_high] ** 2) / (total_energy + 1e-10)
    
    geo_mean = np.exp(np.mean(np.log(magnitude + 1e-10)))
    arith_mean = np.mean(magnitude)
    spectral_flatness = geo_mean / (arith_mean + 1e-10)
    
    high_freq_vals = magnitude[mask_high]
    hf_mean = np.mean(high_freq_vals)
    hf_std = np.std(high_freq_vals)
    peak_count = int(np.sum(high_freq_vals > hf_mean + 3 * hf_std))
    peak_ratio = peak_count / (len(high_freq_vals) + 1e-10)
    
    print(f"  Image size:          {w}x{h}")
    print(f"  Low freq energy:     {low_energy:.6f}")
    print(f"  Mid freq energy:     {mid_energy:.6f}")
    print(f"  High freq energy:    {high_energy:.6f}")
    print(f"  Spectral flatness:   {spectral_flatness:.6f}")
    print(f"  HF peak count:       {peak_count}")
    print(f"  HF peak ratio:       {peak_ratio:.8f}")
    
    score = 0.0
    if peak_ratio > 0.001:
        score += 0.3
    elif peak_ratio > 0.0003:
        score += 0.15
    if spectral_flatness < 0.001:
        score += 0.2
    elif spectral_flatness < 0.01:
        score += 0.1
    if high_energy > 0.3:
        score += 0.2
    elif high_energy < 0.01:
        score += 0.15
    
    print(f"  -> Computed score:   {score:.2f}")


def debug_noise(img):
    """Debug noise analysis."""
    section("LAYER 8: NOISE / PRNU")
    
    from scipy import ndimage, stats as sp_stats
    
    img_arr = np.array(img.convert("RGB"), dtype=np.float64)
    denoised = ndimage.gaussian_filter(img_arr, sigma=3.0)
    residual = img_arr - denoised
    
    flat = residual.flatten()
    variance = float(np.var(flat))
    kurtosis = float(sp_stats.kurtosis(flat, fisher=True))
    skewness = float(sp_stats.skew(flat))
    noise_std = float(np.std(flat))
    
    gray_residual = np.mean(residual, axis=2)
    rows, cols = gray_residual.shape
    left = gray_residual[:, :-1].flatten()
    right = gray_residual[:, 1:].flatten()
    autocorr = float(np.corrcoef(left, right)[0, 1]) if np.std(left) > 1e-10 else 0.0
    
    print(f"  Noise variance:        {variance:.4f}")
    print(f"  Noise std:             {noise_std:.4f}")
    print(f"  Kurtosis:              {kurtosis:.4f}")
    print(f"  Skewness:              {skewness:.4f}")
    print(f"  Spatial autocorrelation: {autocorr:.4f}")
    
    score = 0.0
    if abs(kurtosis) > 5:
        score += 0.25
        print(f"  [FLAG] Abnormal kurtosis")
    if abs(autocorr) < 0.05:
        score += 0.25
        print(f"  [FLAG] Very low spatial correlation — no PRNU fingerprint")
    elif abs(autocorr) > 0.5:
        score += 0.15
        print(f"  [FLAG] High spatial correlation")
    if noise_std < 0.5:
        score += 0.1
        print(f"  [FLAG] Very low noise")
    elif noise_std > 30:
        score += 0.1
        print(f"  [FLAG] Extremely high noise")
    
    print(f"  -> Computed score:   {min(1.0, score):.2f}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_image.py <image_path>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"File not found: {image_path}")
        sys.exit(1)
    
    file_size = os.path.getsize(image_path)
    print(f"File: {image_path}")
    print(f"Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
    
    img = debug_open(image_path)
    if img is None:
        sys.exit(1)
    
    debug_exif(img, image_path)
    debug_ela(img, image_path)
    debug_fft(img)
    debug_noise(img)
    
    section("SUMMARY")
    print("  Debug complete. Review findings above for false positive sources.")


if __name__ == "__main__":
    main()
