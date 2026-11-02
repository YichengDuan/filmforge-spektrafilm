#!/usr/bin/env python3
"""Translate the pinned OFX GLSL spatial kernels to CUDA C++ using GLM.

This is a deliberately narrow syntax translation, not a general GLSL compiler.
The shader arithmetic and operation branches remain in the upstream files.
"""
import argparse
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def translate(path, name):
    source = path.read_text()
    text = re.sub(r'^#version.*$', '', source, flags=re.M)
    text = re.sub(r'layout\(local_size_.*?\) in;', '', text)
    # SSBO arrays become pointers in the by-value kernel descriptor.
    def buffer(match):
        qualifier, body, instance = match.groups()
        qualifier = qualifier or ''
        if instance:
            return 'struct {\n' + body + '\n} ' + instance + ';'
        body = re.sub(r'(\w+) (\w+)\[\];', r'\1* \2 = nullptr;', body)
        if qualifier.strip() == 'readonly':
            body = re.sub(r'(\w+)\*', r'const \1*', body)
        return body
    text = re.sub(r'layout\(std430, binding = \d+\)\s*(readonly\s*)?buffer \w+\s*\{(.*?)\}\s*(\w*)\s*;',
                  buffer, text, flags=re.S)
    text = re.sub(r'layout\(push_constant\) uniform (\w+)\s*\{(.*?)\}\s*(\w+);',
                  r'struct \1 {\2} \3{};', text, flags=re.S)
    text = re.sub(r'^const (float|uint) (k\w+) =', r'static constexpr \1 \2 =', text, flags=re.M)
    # GLSL float literals are single precision; C++ unsuffixed literals are double.
    text = re.sub(r'(?<![\w.])(\d+\.\d*(?:[eE][+-]?\d+)?)(?![\w.])', r'\1f', text)
    # GLM's CUDA function swizzles return values. Expand every writable RGB
    # swizzle explicitly, otherwise += would modify a discarded temporary.
    text = re.sub(r'(\w+)\.rgb\s*([+*/-]?)=\s*([^;]+);',
                  lambda m: f'set_rgb({m[1]}, ' + (f'vec3({m[1]}) {m[2]} ({m[3]})' if m[2] else m[3]) + ');', text)
    text = re.sub(r'\.([rgbaxyzw]{2,4})\b', r'.\1()', text)
    # Every free shader function becomes a device method on its descriptors.
    text = re.sub(r'^(\w+) (\w+)\((.*?)\) \{', r'__device__ \1 \2(\3) {', text, flags=re.M|re.S)
    # The regex above also spans multiline signatures, but never struct bodies.
    text = text.replace('__device__ void main()', '__device__ void run(uvec3 globalInvocationID)')
    text = text.replace('gl_GlobalInvocationID', 'globalInvocationID')
    cached = name in ('Halation','Diffusion')
    if cached:
        replacements = ({
            'gaussianSampleX': 'return ff_blur::gaussian<0,false>(*this,gid,blurKernels[blurKernel]);',
            'gaussianSampleY': 'return ff_blur::gaussian<0,true>(*this,gid,blurKernels[blurKernel]);',
        } if name=='Halation' else {
            'gaussianSampleSourceX': 'return ff_blur::gaussian<1,false>(*this,gid,blurKernels[7+params.componentIndex]);',
            'gaussianSampleTempY': 'return ff_blur::gaussian<2,true>(*this,gid,blurKernels[7+params.componentIndex]);',
            'gaussianSampleSourceXComponent': 'return ff_blur::gaussian<1,false>(*this,gid,blurKernels[7+componentIndex]);',
            'gaussianSampleGroupedTempY': 'return ff_blur::gaussian<3,true>(*this,gid,blurKernels[7+componentIndex],plane);',
            'gaussianSampleDownsampleSourceX': 'return ff_blur::gaussian<4,false>(*this,gid,blurKernels[7+componentIndex],0,reducedWidth,reducedHeight);',
            'gaussianSampleDownsampleTempY': 'return ff_blur::gaussian<5,true>(*this,gid,blurKernels[7+componentIndex],plane,reducedWidth,reducedHeight);',
        })
        for function,body in replacements.items():
            pattern = r'(__device__ \w+ '+function+r'\([^)]*\) \{)'
            text,count = re.subn(pattern,lambda m: m[1]+'\n  if constexpr(Cached) { '+body+' }',text)
            if count!=1:raise RuntimeError(f'Expected one {function}, got {count}')
    declaration = ('template<bool Cached> struct '+name+'Shader {\n'
                   'const ff_blur::Kernel* blurKernels=nullptr;\nint blurKernel=0;\n') if cached else 'struct '+name+' {\n'
    aliases = ('using '+name+'='+name+'Shader<false>;\nusing '+name+'Cached='+name+'Shader<true>;\n') if cached else ''
    return ('// Generated from ' + path.name + ', SHA256 ' + hashlib.sha256(source.encode()).hexdigest() + '\n'
            '// Upstream: chaert-s/spektrafilm-ofx (Aedan Diez), GPL-3.0-only.\n'
            + declaration + text + '\n};\n'+aliases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = '#pragma once\n#include "cuda_blur.cuh"\nnamespace ff_effects {\nusing namespace glm;\nusing uint = unsigned int;\n'
    for name in ('Halation', 'Diffusion', 'Grain'):
        path = ROOT/'upstream/spektrafilm-ofx/shaders/vulkan'/f'Spektra{name}.comp'
        result += translate(path, name)
    result += '} // namespace ff_effects\n'
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result)


if __name__ == '__main__':
    main()
