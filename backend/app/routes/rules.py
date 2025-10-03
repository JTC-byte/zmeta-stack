from __future__ import annotations

from fastapi import APIRouter

from tools.rules import rules

router = APIRouter()


@router.get('/rules')
async def rules_get():
    return {'count': len(rules.set.rules), 'rules': [rule.name for rule in rules.set.rules]}


@router.post('/rules/reload')
async def rules_reload():
    rules.load()
    return {'reloaded': True, 'count': len(rules.set.rules)}


__all__ = ['router']
