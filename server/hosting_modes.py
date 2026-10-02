"""Room-scoped hosting mode policy. Configuration checks do not call providers."""
from fastapi import HTTPException
from .config import settings

MODE_LABELS={'demo':'演示规则脚本','single':'真实单模型','live':'真实双模型'}


def validate_hosting_mode(user,mode):
    if mode not in MODE_LABELS:
        raise HTTPException(422,'不支持的主持模式')
    if mode in ('single','live') and user['guest']:
        raise HTTPException(403,'体验账号不能启用可能付费的模型，请使用正式账号')
    if mode=='single' and not settings.single_ready:
        raise HTTPException(422,'单模型需要服务端决策接口密钥与模型名称；不需要 Gemini')
    if mode=='live' and not settings.live_ready:
        raise HTTPException(422,'双模型尚未配置完整，需要知识顾问与决策接口')
    if mode=='demo' and not settings.enable_demo:
        raise HTTPException(403,'此部署未开启演示模式')
