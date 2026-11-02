cmake_minimum_required(VERSION 3.24)
project(FilmforgeBridge LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(OFX "${CMAKE_SOURCE_DIR}/upstream/spektrafilm-ofx")
set(GENERATED "${CMAKE_SOURCE_DIR}/build/ofx-Release/generated")
add_library(filmforge_vulkan SHARED src/vulkan_bridge.cpp
  "${OFX}/src/SpektraVulkanRenderer.cpp" "${GENERATED}/SpektraGeneratedProfileCurves.cpp")
target_include_directories(filmforge_vulkan PRIVATE "${OFX}/src" "${GENERATED}" "${CMAKE_SOURCE_DIR}/.deps/root/usr/include")
target_link_libraries(filmforge_vulkan PRIVATE /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ${CMAKE_DL_LIBS})

option(FILMFORGE_BUILD_CUDA "Build native CUDA spectral and spatial rendering" OFF)
if(FILMFORGE_BUILD_CUDA)
  set(CMAKE_CUDA_HOST_COMPILER /usr/bin/g++-12 CACHE FILEPATH "CUDA 12 supported host compiler")
  enable_language(CUDA)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  set(CUDA_EFFECTS "${CMAKE_BINARY_DIR}/generated/cuda_effects.cuh")
  add_custom_command(OUTPUT "${CUDA_EFFECTS}"
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/scripts/generate_cuda_effects.py" --output "${CUDA_EFFECTS}"
    DEPENDS scripts/generate_cuda_effects.py
      "${OFX}/shaders/vulkan/SpektraHalation.comp"
      "${OFX}/shaders/vulkan/SpektraDiffusion.comp"
      "${OFX}/shaders/vulkan/SpektraGrain.comp")
  add_library(filmforge_cuda_spectral SHARED src/cuda_spectral.cu src/cuda_spectral_tables.cpp
    "${GENERATED}/SpektraGeneratedProfileCurves.cpp" "${CUDA_EFFECTS}")
  target_include_directories(filmforge_cuda_spectral PRIVATE "${OFX}/src" "${GENERATED}" "${CMAKE_SOURCE_DIR}/.deps/root/usr/include")
  target_include_directories(filmforge_cuda_spectral PRIVATE "${CMAKE_SOURCE_DIR}/src" "${CMAKE_BINARY_DIR}/generated" "${CMAKE_SOURCE_DIR}/.deps/glm")
  set_target_properties(filmforge_cuda_spectral PROPERTIES CUDA_STANDARD 17 CUDA_ARCHITECTURES 86)
  # Keep the rounding policy explicit. Cross-API grain hashes can still differ
  # at cell boundaries. Never enable --use_fast_math for this backend.
  target_compile_options(filmforge_cuda_spectral PRIVATE $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false>)
  target_link_libraries(filmforge_cuda_spectral PRIVATE /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ${CMAKE_DL_LIBS})
endif()
