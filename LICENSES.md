# Source and asset notices

Original bridge code in src/, scripts/, tests/ and comfyui/ is provided under
GPL-3.0-or-later; see LICENSE. The native CUDA port files derived from OFX are
marked GPL-3.0-only and retain the upstream GPLv3 scope. Film modeling powered by spektrafilm by Andrea
Volpato and spektrafilm OFX by Aedan Diez. No endorsement is implied.

Original source: https://github.com/andreavolpato/spektrafilm (GPL v3).
OFX source: https://github.com/chaert-s/spektrafilm-ofx (GPL v3).
SDK: https://github.com/AcademySoftwareFoundation/openfx (BSD 3-Clause and
embedded permissive notices). Keep complete upstream notices in all derived
source/binary distributions.

Original profiles and generated Python LUT assets carry the unchanged
SPEKTRAFILM_LICENSE.txt, CC BY-SA 4.0 with its preamble and attribution. OFX
official binary resources and OFX exported LUT notices are distinct; no official
binary was downloaded/executed or extracted. No permission to redistribute all
possible scientific datasets or third-party binary components is inferred.

See docs/LICENSE_AUDIT.md for the file-by-file inventory and unresolved provenance.
ACKNOWLEDGEMENTS.md records the authors, pinned source links, scientific work
credited by upstream, dependencies, and exactly which integration work was added here.

Native CUDA shader translations retain the upstream OFX GPL and asset notices.
No later-version grant is inferred for upstream source. The generated CUDA
kernels and derived native CUDA implementation use GPL-3.0-only notices.
GLM 1.0.1 (G-Truc Creation) is used under its MIT license; full notice remains in
.deps/glm/copying.txt and build/cuda-spectral/GLM-LICENSE.txt after the CUDA build.
The CUDA toolkit is an existing local build dependency, not redistributed here.
