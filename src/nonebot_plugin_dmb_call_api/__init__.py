from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters import Message
from nonebot.params import CommandArg, ArgPlainText
from pydantic import BaseModel
from nonebot import get_plugin_config
import traceback
import httpx
import yaml
import json


class Config(BaseModel):
    dmb_forwards_config_file: str = "data/discord_message_bridge_forwards.yaml"


env = get_plugin_config(Config)
with open(env.dmb_forwards_config_file, 'r', encoding='utf-8') as f:
    config = yaml.load(f, Loader=yaml.FullLoader)
bots = config["discord-bots"]

process = {}
dca = on_command("dmb-call-api", aliases={"dca"}, priority=0, block=True, permission=SUPERUSER)


@dca.handle()
async def handle_function(event, args: Message = CommandArg()):
    action = args.extract_plain_text().strip().split(" ")
    if not action:
        await dca.finish("使用 help 查看可用选项", reply_message=True)
    match action[0]:
        case "help":
            await dca.finish('''可用选项有:
help - 显示此消息
list - 显示可用的 Bot 列表
call <bot-id> - 调用 Discord Api''', reply_message=True)
        case "list":
            reply = ""
            async with httpx.AsyncClient() as client:
                for num, token in bots.items():
                    reply += f"Bot {num}: {token[:4]}***{token[-4:]}\n"
                    r = await client.get(f"https://discord.com/api/v9/users/@me",
                                         headers={"Authorization": f"Bot {token}"})
                    try:
                        reply += f"  {r.json()['username']}#{r.json()['discriminator']}\n"
                    except Exception:
                        reply += "  获取用户信息失败\n"
                    reply += "\n"
            await dca.finish(reply, reply_message=True)
        case "call":
            if len(action) < 2:
                await dca.finish("参数错误", reply_message=True)
            if action[1] not in bots:
                await dca.finish("Bot 不存在", reply_message=True)
            headers = {"Authorization ": f"Bot {bots[action[1]]}"}
            global process
            process[event.get_user_id()] = [headers]


@dca.got("method", prompt="请输入请求方法:\nGET, POST, PUT, PATCH, DELETE\n使用 CANCEL 取消")
async def got_method(event, method: str = ArgPlainText()):
    global process
    method = method.upper()
    if method == "CANCEL":
        await dca.finish("已取消", reply_message=True)
        del process[event.get_user_id()]
    if method not in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
        await dca.reject_arg("请求方法错误! 请重新输入")
    process[event.get_user_id()].append(method)


@dca.got("url", prompt="请输入请求地址:\n可以省略 Base URL\n使用 CANCEL 取消")
async def got_url(event, url: str = ArgPlainText()):
    global process
    if url.upper() == "CANCEL":
        await dca.finish("已取消", reply_message=True)
        del process[event.get_user_id()]
    if url.startswith("https://"):
        process[event.get_user_id()].append(url)
    elif url.startswith("/"):
        process[event.get_user_id()].append(f"https://discord.com/api/v9{url}")
    else:
        await dca.reject_arg("请求地址错误! 请重新输入")


@dca.got("data", prompt="请输入请求数据(body,application/json):\n不需要请输入 NONE\n使用 CANCEL 取消")
async def got_data(event, data: str = ArgPlainText()):
    global process
    if data.upper() == "CANCEL":
        await dca.finish("已取消", reply_message=True)
        del process[event.get_user_id()]
    if data.upper() == "NONE":
        process[event.get_user_id()].append(None)
    else:
        try:
            data = json.loads(data)
            if type(data) == dict:
                process[event.get_user_id()].append(data)
            else:
                await dca.reject_arg("数据类型应为 dict\n请求数据错误! 请重新输入")
        except Exception:
            await dca.reject_arg(traceback.format_exc().split("\n")[-2] + "\n请求数据错误! 请重新输入")
    if len(process[event.get_user_id()]) == 4:
        headers, method, url, data = process[event.get_user_id()]
        async with httpx.AsyncClient() as client:
            try:
                r = await client.request(method, url, headers=headers, json=data)
                await dca.finish(f"{r.json()}", reply_message=True)
            except Exception:
                await dca.finish(traceback.format_exc().split("\n")[-2], reply_message=True)
        del process[event.get_user_id()]
