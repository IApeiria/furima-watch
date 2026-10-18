# furima-watch — 日本二手平台横跨比价提醒工具

[日本語](README.md) | [English](README.en.md) | **简体中文**

想要的二手商品一出现在你设定的价格以下，就立刻弹出 Windows 通知。
运行一次就会搜遍 7 个网站：Mercari（煤炉）、雅虎拍卖、PayPay 跳蚤市场、Rakuma、Janpara、Sofmap、Hard Off。

最初是为了便宜买到一块 RTX 4070 Ti SUPER 而做的。改一下配置文件，就能监视任何商品。

## 功能

- 横跨 7 个网站，寻找价格符合条件的新上架商品
- 用正则表达式过滤标题，只留下商品本体（排除空盒、线材、整机、回收广告等）
- 雅虎拍卖不只看一口价，**快结束且当前出价很低**的拍卖也会提醒
- 已经提醒过的商品会记住，不会重复提醒（降价后重新符合条件会再提醒）
- 点击通知直接打开商品页面。配合 [ntfy.sh](https://ntfy.sh) 也能推送到手机
- 某个网站连续抓取失败（比如页面结构改了）时，会提醒你一次

## 使用方法

需要 Python 3.11 以上（适用于 Windows，通知使用 winotify）。

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.toml config.toml   # 写上想买的东西和价格
.venv\Scripts\python furima_watch.py --dry-run      # 不发通知，只显示符合条件的商品
.venv\Scripts\python furima_watch.py --test-notify  # 预览通知效果
.venv\Scripts\python furima_watch.py                # 巡查一次，有新商品就通知
```

### 定时运行（任务计划程序）

脚本巡查一次就结束，所以用 Windows 任务计划程序每 15–30 分钟运行一次。
用 `pythonw.exe` 运行不会弹出命令行窗口。

```bash
schtasks /create /tn furima-watch /sc minute /mo 20 /tr "\"C:\path\to\furima-watch\.venv\Scripts\pythonw.exe\" \"C:\path\to\furima-watch\furima_watch.py\""
```

## 配置（config.toml）

每个想监视的商品写一个 `[[watch]]`。完整示例见 [config.example.toml](config.example.toml)（注释为日语）。

| 项目 | 含义 |
|---|---|
| `name` | 通知里显示的名字 |
| `queries` | 在跳蚤市场和拍卖网站搜索的关键词（可以写多个） |
| `shop_query` | 在 Janpara、Sofmap、Hard Off 搜索的关键词（省略时用 `queries` 的第一个） |
| `min_price` / `max_price` | 价格范围（日元）。建议设下限：太便宜的多半是盒子或线材 |
| `target` | 标题匹配其中任意一个就算目标商品（正则列表；为空则搜索结果全部算） |
| `exclude` | 标题匹配其中任意一个就排除 |
| `include_junk` | 是否包括故障品（ジャンク） |

匹配前，标题会经过 NFKC 规范化并转成小写，全角字符会变成半角，所以正则请用半角字符书写。

## 注意

- 使用的是各网站非官方的获取方式，网站改版后可能失效。
- 请仅限个人使用，巡查间隔设长一些，避免给网站造成负担。各网站的使用条款请自行确认。
- 购买前请务必亲自查看商品页面。

## License

MIT
