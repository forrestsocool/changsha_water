# 长沙水费 Home Assistant 集成

在 Home Assistant 中查询长沙供水余额、账单和用水量，并在明细 Token 失效时继续用余额变化估算每日用水，不会因为充值把日用量减成负数。

[![Open your Home Assistant instance and open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=forrestsocool&repository=changsha_water&category=integration)

## 功能

- 余额接口不需要 Token，默认每 5 分钟查询一次。
- 明细接口需要用户 ID 和 Token，默认每 6 小时查询一次。
- 提供余额、推算总用水量、今日用水量、今日水费、今日充值下限、水价、账单与累计数据。
- 支持 Home Assistant 长期统计；`推算总用水量` 可作为水量统计源。
- Token 失效后，余额查询与本地日级推算继续工作。
- 在通知中心和“修复”面板提醒用户抓包更新 Token，并自动启动重新认证流程。
- 所有持久化推算数据保存在 Home Assistant 私有存储中。
- 配置标题、设备序列号、唯一 ID 和诊断信息均脱敏；不会把完整水表号、用户 ID、Token、姓名或地址写入日志和实体属性。
- Home Assistant 2026.3+ 直接加载集成内置品牌图标，不依赖远程图片。

## 安装

### HACS

点击 README 顶部的 HACS 按钮，或者手动添加自定义仓库：

```text
https://github.com/forrestsocool/changsha_water
```

类别选择 `Integration`。安装后重启 Home Assistant。

### 手动安装

把 `custom_components/changsha_water` 复制到 Home Assistant 配置目录下的 `custom_components/changsha_water`，然后重启。

最低支持 Home Assistant `2026.3.0`。

## 配置

进入“设置 → 设备与服务 → 添加集成”，搜索“长沙水费”，只需填写三个字段：

1. 水表号
2. 用户 ID，即请求头 `x-tif-loginUserid` 和请求体 `loginId`
3. Token，即抓包中的 `x-tif-token`

三个字段都是隐私数据，配置流不会提供默认值，也不会在重新配置或重新认证时回显旧值。请不要把真实值提交到 Issue、日志或截图中。

配置时会同时验证：

- 水表号能通过免 Token 余额接口查询；
- Token 能访问明细接口；
- 该用户 ID 下确实包含填写的水表号。

## 数据与实体

| 实体 | 数据来源 | 说明 |
| --- | --- | --- |
| 余额 | 余额接口 | 当前水费余额，CNY |
| 推算总用水量 | 本地账本 + 明细锚点 | 单调累计，适合长期统计 |
| 欠费 / 滞纳金 / 允许缴费 | 余额接口 | 服务端当前缴费状态 |
| 今日用水量 | 余额差额 / 最近水价 | 每日自动归零 |
| 今日水费 | 余额下降量 | 充值不会倒扣 |
| 今日充值下限 | 余额上升量 | 只表示两次采样之间可确认的最小充值额 |
| 推算水价 | 最近账单或累计数据 | 优先使用 `last_amount / last_water` |
| 接口总用水量 | 明细接口 | 服务端原始累计水量 |
| 最近账单用水量/金额 | 明细接口 | Token 有效时更新 |
| 累计水费 | 明细接口 | 服务端累计金额 |
| Token 异常 | 明细接口 | 异常时打开，同时启用降级推算 |

## 充值与日级推算

余额本质上不是水表读数。直接用“昨天余额 - 今天余额”会在充值时得到负数，本集成采用一个单调账本：

1. 余额下降：差额计入当日水费；若已有水价，再换算为用水量。
2. 余额上升：识别为当天充值下限，不减少任何已记录用量。
3. 同一天再次出现余额上升：按“每天最多充值一次”的业务规则记为余额调整，仍不产生负用量。
4. Token 有效时：用明细接口的 `total_water` 做权威锚点。
5. 明细数据后来追上已推算的用量时：只消除待核对差额，不重复累计。
6. 明细增量大于余额已推算增量时：只补缺少的部分。

充值发生在两次余额查询之间时，同一间隔内的少量消费无法仅靠余额精确拆分，因此“今日充值下限”不是充值凭证的精确金额。默认 5 分钟轮询可把这部分误差压到较小；明细恢复后还会用累计水量补差。

## Token 失效与降级

明细接口返回 Token 过期或无权限时：

- 不卸载集成；
- 不影响免 Token 余额接口；
- 保留最近一次明细和水价；
- 继续使用余额变化推算日用量；
- 创建固定 ID 的持久通知和修复项，不会每次轮询重复刷屏；
- 启动 Home Assistant 重新认证流程。

处理方法：

1. 在手机端重新进入供水服务并抓包。
2. 找到明细请求中的 `x-tif-loginUserid` 和 `x-tif-token`。
3. 在 Home Assistant 通知或集成页面打开“重新认证”。
4. 手动填写用户 ID 和新 Token。

重新认证成功后通知和修复项会自动清除，明细锚点恢复，期间的余额推算不会丢失。

## 更新频率

集成选项中可以设置：

- 余额查询：1–60 分钟，默认 5 分钟；
- 明细查询：30–1440 分钟，默认 360 分钟；
- 本地日记录：7–366 天，默认 90 天。

不建议无必要地把免 Token 接口设置为 1 分钟，也不建议高频请求需要 Token 的明细接口。

## 隐私与诊断

- Home Assistant 的 config entry 必须保存三个配置值才能调用接口，请保护好配置目录和备份。
- 本地日账本使用 `private=True` 存储。
- 设备名只显示水表号末四位，注册表唯一 ID 使用 SHA-256 指纹。
- 下载诊断时，水表号、用户 ID、Token 会被 Home Assistant 的诊断脱敏工具删除。
- API 返回的姓名、地址、设备编号不会进入实体状态、属性或诊断。

## 设计参考

数据建模遵循 Home Assistant 官方的[传感器长期统计规范](https://developers.home-assistant.io/docs/core/entity/sensor/)；充值和复位处理思路参考官方 [Utility Meter](https://www.home-assistant.io/integrations/utility_meter/) 对累计量、差值和复位的处理原则。集成使用两个独立更新协调器，使免 Token 余额链路不会被认证链路拖垮。

## 免责声明

这是非官方社区集成，仅供用户查询自己的供水账户。上游接口、字段和鉴权规则可能随时变化。请遵守服务条款和当地法律，不要对接口进行高频或未经授权的访问。
