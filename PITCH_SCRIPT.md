# Pitch Script

## Two-Minute Version

This project is an AI fraud detector for image-based claim review.

The problem we are solving is simple: if someone submits an image as evidence for a refund, dispute, or claim, a single detector is not enough. One model can miss a new generator, overreact to compression, or get confused by stylized but genuine photos.

So instead of relying on one model, we built a multi-signal decision system.

Here is how it works.

The user uploads an image through a Next.js frontend. That image is sent to a FastAPI backend along with optional context like account ID, device fingerprint, and order value.

Once the backend receives the file, it validates the format and size, stores it, and pre-processes it once so the system does not waste memory decoding the same image for every detector.

Then the main pipeline runs 21 checks in parallel.

Those checks come from different evidence families.

First, we run provenance checks like EXIF metadata and C2PA credentials to see whether the file behaves like a real camera capture or carries authenticated origin data.

Second, we run duplicate-fraud checks using perceptual hashes so we can tell if the same image, or a near-duplicate, has already been used in earlier claims.

Third, we run learned image detectors like CLIP and TruFor. These are strong model-based signals that look for patterns common in generated or manipulated imagery, and TruFor can even return a heatmap showing suspicious regions.

Fourth, we run a semantic vision-language layer using Gemini, with a local fallback model if needed. That layer looks for things like impossible reflections, broken text, unnatural edges, or physically inconsistent details.

Fifth, we run statistical and forensic heuristics like error-level analysis, neighboring-pixel relationships, entropy patterns, spectral analysis, and texture regularity. These are useful because generators often leave structural traces even when the image looks convincing to a human.

After that, the system does not just average everything together. Each layer returns both a suspicion score and a confidence value. The scoring engine uses configured weights, reduces the impact of brittle or low-confidence signals, rewards agreement across independent evidence families, and has overrides for very strong evidence.

For example, if we find an exact perceptual hash match to a previous suspicious claim, that pushes the result very high. If we find strong authenticated C2PA provenance, that can push the result very low.

The result is a final risk score, a risk tier, plain-language reasons for a reviewer, and a technical breakdown for an analyst.

So the real value of this project is not just AI-image detection. It is explainable fraud decisioning for image submissions.

## One-Minute Version

We built an image fraud-review engine that does not rely on one fragile detector. A user uploads an image, the backend runs 21 parallel checks across provenance, duplicate-image history, learned models, semantic reasoning, and statistical forensics, and then a scoring engine weights the reliable signals, suppresses weak ones, and produces a final risk verdict. The frontend shows both a simple reviewer summary and a detailed forensic breakdown, so the system is useful for both operations teams and technical analysts.

## Short Demo Narration

When I upload an image, the frontend sends it to the backend for full analysis. The backend validates it, pre-processes it once, and fans it out to 21 detectors in parallel. Some layers check metadata and provenance, some compare the image to historical claims, some use trained models like CLIP and TruFor, and others use statistical forensic methods that look for generation artifacts. The scoring engine then combines those signals into a single risk score with explanations, and the UI presents the result as both a plain-language verdict and a technical layer-by-layer report.

## Key Talking Points

- This is a decision system, not just a classifier.
- Multiple evidence families reduce the risk of one model being wrong.
- Duplicate-history and behavioral context make it operationally useful, not just academically interesting.
- The system is explainable because every layer reports its own score, confidence, and evidence.
- The UI supports both non-technical reviewers and technical investigators.
