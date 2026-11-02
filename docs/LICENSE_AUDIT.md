# License audit

This is an engineering inventory, not a legal opinion. Source snapshots and
complete notices remain in upstream/. No official binary distribution is imported.

* Original `LICENSE`: GNU GPL v3. New bridge code is delivered under GPL-3.0-or-later.
* Original `SPEKTRAFILM_LICENSE.txt`, preamble v1.1 (2026-05-28): profiles and
  direct derivatives, including LUT encodings, are CC BY-SA 4.0. Preserve Andrea
  Volpato attribution, canonical repository URL, license and modification notice.
  This current preamble explicitly distinguishes nonbinding requests (including
  not reselling LUT packs and not commercial AI training) from the legal floor.
  The current README has contradictory older wording about a strict no-resale
  license; do not use that wording to silently substitute the full license file.
  Keep the original file verbatim with generated local assets.
  The second copy at src/spektrafilm/data/license/SPEKTRAFILM_LICENSE.txt was
  checked and is byte-identical to the root license; official generated bundles
  preserve that same notice.
* OFX root `LICENSE.txt`: GPL v3, separate from official binary terms.
* OFX `Legal/SPEKTRAFILM_OFX_LICENSE.txt`: official binaries may include non-GPL
  licensed standards/runtime resources. Custom builds made solely from public GPL
  sources and redistributable resources remain GPL. Never extract resources from
  the official distribution for this bridge.
* OFX `Legal/SPEKTRAFILM_OFX_LUT_LICENSE.txt`: exported LUTs bearing that notice
  have separate no-resale/product/service restrictions. Do not treat them as
  interchangeable with original Python CC BY-SA LUT assets. No OFX LUTs are
  redistributed here.
* OFX `Legal/THIRD_PARTY_NOTICES.txt`: credits Andrea Volpato, Johannes Hanika /
  vkdt spectral upsampling, Mallett/Yuksel, and OpenFX. Keep intact in builds.
* OpenFX SDK tag OFX_Release_1.5.1: BSD 3-Clause; ofxKeySyms.h additionally
  contains X Consortium and DEC permissive notices. Preserve these files.
* Ubuntu packages and Python dependencies retain their individual licenses;
  .deb packages are downloaded/extracted locally, not installed globally.

Uncertainty: the public OFX standards/profile data provenance is only partially
described by the notices. Custom building does not settle rights to all embedded
scientific datasets. Before public binary/data redistribution, obtain upstream
clarification. Current outputs are local test artifacts, not a published LUT pack.
Using a subprocess helps dependency isolation; it does not waive license duties.

## Native CUDA addition (2026-11-02)

The CUDA arithmetic is derived from the same pinned GPL OFX shader/CPU helpers,
not a newly licensed film algorithm. Upstream author attribution remains in the
generator and generated kernels. Profile/asset restrictions above still apply.
Derived CUDA source/header files and generated kernels are marked GPL-3.0-only;
the separate original bridge remains GPL-3.0-or-later. No extra later-version
permission is inferred from the OFX repository's GPL-3.0 notice.
GLM 1.0.1, SHA 0af55ccecd98d4e5a8d1fad7de25ba429d60e863, is fetched from
https://github.com/g-truc/glm and used under its MIT option (G-Truc Creation,
2005 onward); the complete copying.txt remains in the clone and is copied to
build/cuda-spectral/GLM-LICENSE.txt. GLM source is not republished here.
The existing NVIDIA CUDA Toolkit is used for local compilation. No CUDA toolkit,
driver, runtime distribution or compiled Filmforge binary is published by this
source repository; binary redistributors must separately check NVIDIA terms.
