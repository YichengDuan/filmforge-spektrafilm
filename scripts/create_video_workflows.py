#!/usr/bin/env python3
"""Create portable ComfyUI UI workflows and matching tested API prompts."""
import copy
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]


def node(id,kind,pos,size,inputs,outputs,values,title=None):
    n={'id':id,'type':kind,'pos':pos,'size':size,'flags':{},'order':id-1,'mode':0,
       'inputs':inputs,'outputs':outputs,'properties':{'Node name for S&R':kind},'widgets_values':values}
    if title: n['title']=title
    return n


def socket(name,type,link=None,widget=False):
    s={'name':name,'type':type,'link':link}
    if widget: s['widget']={'name':name}
    return s


def output(name,type,links=None):
    return {'name':name,'type':type,'links':links}


def create(backend):
    fast=backend=='cuda-lut'
    native=backend=='cuda-spectral'
    label='CUDA-LUT 快速调色（仅颜色）' if fast else ('CUDA 原生光谱与空间效果' if native else 'Vulkan 胶片调色')
    prefix='filmforge_video/cuda_fast' if fast else ('filmforge_video/cuda_native' if native else 'filmforge_video/vulkan_full')
    preset={'film':'kodak_vision3_500t','print_profile':'kodak_2383','backend':backend,
            'grain':0 if fast else .25,'halation':0 if fast else .25,'diffusion':0 if fast else .1,
            'seed':1234,'temporal_grain_correlation':0,'exposure':0}
    api={
      '1':{'class_type':'LoadVideo','inputs':{'file':'filmforge_demo_10s.mp4'}},
      '2':{'class_type':'GetVideoComponents','inputs':{'video':['1',0]}},
      '3':{'class_type':'SpektrafilmPreset','inputs':preset},
      '4':{'class_type':'SpektrafilmVideoFrames','inputs':{'images':['2',0],'preset_json':['3',0],'fps':['2',2],'start_frame':0,'input_transfer':'bt709'}},
      '5':{'class_type':'CreateVideo','inputs':{'images':['4',0],'fps':['4',1],'audio':['2',1],'bit_depth':'auto','color_space':'sRGB','codec':'none'}},
      '6':{'class_type':'SaveVideo','inputs':{'video':['5',0],'filename_prefix':prefix,'format':'mp4','format.codec':'h264'}}}
    graph={'last_node_id':7,'last_link_id':8,'nodes':[
      node(1,'LoadVideo',[20,80],[290,240],[],[output('VIDEO','VIDEO',[1])],['filmforge_demo_10s.mp4'],'1. 选择输入视频 / SDR'),
      node(2,'GetVideoComponents',[370,100],[250,190],[socket('video','VIDEO',1)],
           [output('images','IMAGE',[2]),output('audio','AUDIO',[3]),output('fps','FLOAT',[4]),output('bit_depth','COMBO'),output('color_space','COMBO')],[],
           '2. 拆分帧、原音轨和帧率'),
      node(3,'SpektrafilmPreset',[20,400],[330,370],[],[output('preset_json','STRING',[5])],list(preset.values()),'3. '+label),
      node(4,'SpektrafilmVideoFrames',[690,120],[330,230],
           [socket('images','IMAGE',2),socket('preset_json','STRING',5,True),socket('fps','FLOAT',4,True)],
           [output('images','IMAGE',[6]),output('fps','FLOAT',[7])],['',25,0,'bt709'],'4. 逐帧胶片调色 / 选择输入 transfer'),
      node(5,'CreateVideo',[1090,110],[300,250],
           [socket('images','IMAGE',6),socket('fps','FLOAT',7,True),socket('audio','AUDIO',3)],
           [output('VIDEO','VIDEO',[8])],[25,'auto','sRGB','none'],'5. 合回原音轨与帧率'),
      node(6,'SaveVideo',[1470,90],[340,350],[socket('video','VIDEO',8)],
           [output('video','VIDEO')],[prefix,'mp4','h264','auto'],'6. 导出 MP4 / H.264'),
      node(7,'Note',[410,460],[650,260],[],[],[
          '用法：选择视频，调整胶片/相纸/exposure，然后运行。原音轨和 fps 自动连接。\n'
          +('CUDA-LUT 是 65³ 颜色近似。grain/halation/diffusion/temporal correlation 必须为 0。首用或更换配置会生成本机 LUT 缓存。\n' if fast else ('原生 CUDA 移植 81 波段色彩链、密度颗粒、曝光阶段 halation 与 camera diffusion。覆盖当前节点功能；未覆盖 OFX 的全部高级参数。\n' if native else 'Vulkan 执行上游光谱模型，支持 grain、曝光阶段 halation、camera diffusion。\n'))
          +'演示输入为 BT.709：input_transfer=bt709；若是 ComfyUI 保存的 sRGB 视频，改选 srgb。HDR/Log 需先转换。输出为 SDR sRGB / H.264。视频批次占系统内存，长片请分段并设置绝对 start_frame。\n'
          +'测试 GPU 为 A2000。安装或更新后重启 ComfyUI，再选择后端。'],
           '说明 / Important')],
      'links':[[1,1,0,2,0,'VIDEO'],[2,2,0,4,0,'IMAGE'],[3,2,1,5,2,'AUDIO'],[4,2,2,4,2,'FLOAT'],
               [5,3,0,4,1,'STRING'],[6,4,0,5,0,'IMAGE'],[7,4,1,5,1,'FLOAT'],[8,5,0,6,0,'VIDEO']],
      'groups':[],'config':{},'extra':{'ds':{'scale':.7,'offset':[30,30]}},'version':.4}
    return graph,api


for name,backend in [('Filmforge_Video_Full_Vulkan','vulkan'),('Filmforge_Video_Fast_CUDA_LUT','cuda-lut'),('Filmforge_Video_Native_CUDA','cuda-spectral')]:
    graph,api=create(backend)
    (root/f'examples/{name}.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2))
    (root/f'examples/{name}.api.json').write_text(json.dumps(api,ensure_ascii=False,indent=2))
    print(name)
