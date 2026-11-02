cmake_minimum_required(VERSION 3.24)
project(FilmforgeBridge LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(OFX "${CMAKE_SOURCE_DIR}/upstream/spektrafilm-ofx")
set(GENERATED "${CMAKE_SOURCE_DIR}/build/ofx-Release/generated")
add_library(filmforge_vulkan SHARED src/vulkan_bridge.cpp
  "${OFX}/src/SpektraVulkanRenderer.cpp" "${GENERATED}/SpektraGeneratedProfileCurves.cpp")
target_include_directories(filmforge_vulkan PRIVATE "${OFX}/src" "${GENERATED}" "${CMAKE_SOURCE_DIR}/.deps/root/usr/include")
target_link_libraries(filmforge_vulkan PRIVATE /usr/lib/x86_64-linux-gnu/libvulkan.so.1 ${CMAKE_DL_LIBS})
