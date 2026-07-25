# Team J Extensible API: Method and Execution

## 一句话目标

前端只认识一种车辆格式；Partly、本地 CSV、未来 VIN/OEM 服务都通过
Provider 转换成这种格式。新增数据来源时增加 Provider，不重写网站。

## 已经实施的 14 个步骤

### Step 1：建立统一车辆格式

每辆车都有：

```json
{
  "id": "local:唯一编号",
  "provider_key": "数据源内部编号",
  "make": "Toyota",
  "model": "Corolla",
  "year": 2022,
  "trim": "GX",
  "source": "local_catalogue",
  "capabilities": {
    "damage_prediction": false,
    "oem_parts": true,
    "diagram": false
  }
}
```

`capabilities` 让界面如实展示能力，不会把没有 AI 或零件图的车辆假装成
全功能车辆。

### Step 2：用统一 ID 区分来源

- `partly:ford-ranger-demo`：数据由 Partly Provider 读取。
- `local:550e8400-...`：数据由本地 SQLite Provider 读取。

Service 根据冒号前面的来源选择正确 Provider。

### Step 3：建立 Provider 合同

每个车辆数据源都实现：

```python
list_vehicles()
get_vehicle(provider_key)
get_parts(provider_key)
```

位置：`app/providers/base.py`。

### Step 4：实现 Partly Provider

`app/providers/partly.py` 调用官方 API，并把原始字段转换成统一格式。已有
8 辆车、预测、assemblies、OEM number 和图继续完整工作。

### Step 5：实现 Local Catalogue Provider

`app/providers/local_catalogue.py` 从 SQLite 读取维修员新增的车辆与零件，
并根据是否存在零件、图片自动计算 `capabilities`。

### Step 6：建立长期数据表

`app/database.py` 新增：

- `local_vehicles`：车辆身份、年份、版本、VIN。
- `local_parts`：零件名称、OEM number、类别和可选图片链接。

原有 `cases`、`case_items`、`manual_regions` 继续保存核验历史。

### Step 7：用 Service 合并来源

`VehicleService` 并行请求所有 Provider 并合并结果。某个 Provider 失败时，
其他来源仍返回数据。因此 Partly 离线时，本地车辆仍能工作。

`AssessmentService` 按来源选择两种流程：

- Partly：AI prediction → OEM 匹配 → impact path → 维修员核验。
- Local：导入目录 → 维修员选择损坏零件 → OEM 核验。

### Step 8：建立版本化 API

已实现：

| 接口 | 执行内容 |
|---|---|
| `GET /api/v1/vehicles` | 合并全部车辆 |
| `POST /api/v1/vehicles` | 新增本地车辆 |
| `GET /api/v1/vehicles/{id}/parts` | 查询统一零件 |
| `POST /api/v1/vehicles/{id}/parts` | 添加单个零件 |
| `GET /api/v1/vehicles/{id}/assessment` | 建立对应核验流程 |
| `POST /api/v1/catalogues/import` | 批量导入 CSV |

### Step 9：实现前端执行入口

网站中的 **Add new vehicle** 会：

1. 调用 `POST /api/v1/vehicles`。
2. 如果选择 CSV，调用 `/api/v1/catalogues/import`。
3. 重新读取统一车辆列表。
4. 自动选择新车辆。
5. 显示该车辆真正拥有的功能。

选中已创建的本地车辆后，还可以继续导入 CSV。重复的
`part_name + oem_number` 会更新，不会重复增加。

### Step 10：保留人工核验与历史

Partly 车辆和本地车辆最终都写入同一套 case 数据：

```text
车辆/照片信息
→ 候选零件
→ 维修员确认、否认或修正
→ SQLite 历史
→ CSV 报告
```

这让后续的历史案例检索不依赖数据最初来自 Partly 还是本地目录。

### Step 11：增加真实照片入口

`POST /api/v1/photo-assessments/analyse` 接收 1–4 张图片。后端会：

1. 验证 JPEG、PNG 或 WEBP；
2. 限制单张与总大小；
3. 修正 EXIF 方向；
4. 缩放异常大图；
5. 重新编码并移除原始元数据；
6. 只通过受控 API 返回保存的照片。

### Step 12：增加可替换 Vision Provider

`app/vision.py` 提供：

- `OpenAIVisionProvider`：真实多图视觉推理和严格结构化输出；
- `WebhookVisionProvider`：连接团队自训的部件/损伤分割模型；
- `guided_result`：没有模型时的明确人工演示，不冒充 AI。

视觉层只返回可见部位、损伤、严重度、置信度和区域，不生成 OEM。

### Step 13：增加 part_relations 与传播概率

SQLite 的 `part_relations` 保存零件连接、关系类型、权重和适用撞击区域。
`ImpactPropagationService` 最多传播三层，逐层衰减并保留完整路径。

输出标签：

- `visible_damage`：照片直接观察；
- `impact_path`：推荐检查的隐藏零件；
- `manual`：维修员输入。

传播项默认是 `Needs inspection`，不会自动设成 `Confirm`。

### Step 14：照片结果与案例关联

新增 `photo_assessments` 和 `assessment_images`，并让
`cases.photo_run_id` 关联最终维修记录。CSV 现在会包含：

- 损伤类型与严重度；
- 照片证据 ID 与框；
- 判断理由；
- 传播路径；
- 概率等级。

## 现场演示执行顺序

### 演示 A：Partly 完整链路

1. 启动官方 API。
2. 选择 Partly demo vehicle。
3. Run assessment。
4. 展示 prediction、OEM、diagram 和 impact checks。
5. 修改 technician decision。
6. 保存并导出 CSV。

### 演示 A+：真实照片链路

1. 设置 `OPENAI_API_KEY` 后启动网站。
2. 选择有 OEM 目录的车辆。
3. 上传 3–4 张事故照片。
4. 展示绿色可见损伤框、损伤类型和置信度。
5. 展示 `Impact check` 的概率等级与完整传播路径。
6. 说明它是检查排序而非内部损坏诊断。
7. 维修员确认 OEM 候选并保存。

### 演示 B：突破 8 辆车限制

1. 点击 Add new vehicle。
2. 输入 `Toyota / Corolla / 2022 / GX`。
3. 上传 `app/static/catalogue-template.csv`。
4. 新车立刻出现在 Locally added vehicles 分组。
5. Run assessment。
6. 点击 Add missing part。
7. 从输入建议中选择导入的零件，OEM number 自动填入。
8. 保存并导出 CSV。

### 演示 C：Provider 故障隔离

1. 停止官方 Partly API。
2. 刷新 Team J。
3. 状态显示 Partly offline。
4. 本地车辆仍能打开、选零件、保存和导出。

这证明扩展性不是“手动伪造更多车名”，而是系统已经拥有可接入多个真实
数据源的结构。

## 后续扩展方法

### 接 VIN API

新增 `VinProvider`，实现统一 Provider 方法，并在
`app/dependencies.py` 注册。前端车辆格式不变。

### 接正式 OEM 服务

新增 `OemProvider.get_parts()`，将外部字段映射成：

```json
{
  "part_id": "...",
  "part_name": "...",
  "oem_number": "...",
  "category": "...",
  "diagram_url": "..."
}
```

### 接新的损伤识别 AI

不需要重写 Assessment Service。设置 `VISION_PROVIDER=webhook`，让专门模型
按 `app/vision.py` 的 `VisionResult` 返回通用损伤名称、置信度、严重度和
区域，再由 OEM Provider 匹配具体零件。

## 能力边界

- 创建 API 解决的是接入、统一、保存和扩展。
- OEM number 必须来自真实目录或正式服务，不能凭空生成。
- 本地车辆没有 Partly prediction 时不会伪装成 AI 结果。
- 图片 URL、VIN、车型版本和最终维修决定仍需可信来源或维修员确认。
- 通用视觉模型提供方框而非像素级 mask；像素分割需接专门 webhook。
- 传播概率用于排序拆检优先级，不等于物理仿真或确定损坏概率。
