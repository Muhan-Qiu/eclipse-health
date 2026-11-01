# Open Food Facts · eclipse health 模块

官方 `data-source` 模块，适配自 [openfoodfacts/openfoodfacts-python](https://github.com/openfoodfacts/openfoodfacts-python)。
按 EAN/UPC 条码查询食品营养，返回每 100g 营养与按摄入量换算的营养记录。
**非医疗器械，不用于诊断。**

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` / `warmup` / `health` | 握手；`health` 报告依赖与联网要求 |
| `lookup` | `{barcode}` → `{found, barcode, product, attribution}`；也是页面表单与工具 `food.lookup` 入口 |
| `mapProduct` | `{barcode, consumedGrams?}` → `nutrition.entry` record payload |
| `latestProduct` | 本进程最近一次产品，供页面 detail 与 widget |
| `deactivate` | 退出 |

## 数据许可与网络

- 只访问 `world.openfoodfacts.org`；
- 数据 © Open Food Facts contributors，**ODbL 1.0**：保留署名与同源要求，不回写第三方数据；
- 条目由社区贡献，字段可能缺失或过期；页面与结果均带非诊断声明。

## 适配说明

- `src/adapter.py` 纯函数处理条码校验、营养字段归一、kJ→kcal 与摄入量换算；
- `openfoodfacts` 只在查询时导入；网络失败返回 `MODULE_ERROR`，不泄露 URL；
- 页面使用声明式 `form` + `detail`，引用本模块 `lookup` / `latestProduct`。

## 许可与署名

- 本适配层：GPL-3.0-only；上游 MIT，署名见 `NOTICE`；
- 上游 LICENSE 需在发布前放入 `LICENSES/openfoodfacts-upstream.txt`。
