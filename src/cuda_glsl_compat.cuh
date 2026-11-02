// GPL-3.0-or-later. GLSL vector operations for the native CUDA shader port.
#pragma once
#include <cuda.h>
#define GLM_FORCE_SWIZZLE
#include <glm/glm.hpp>
#include <glm/gtc/epsilon.hpp>
__device__ inline void set_rgb(glm::vec4& value, glm::vec3 rgb) {
  value.x=rgb.x; value.y=rgb.y; value.z=rgb.z;
}
