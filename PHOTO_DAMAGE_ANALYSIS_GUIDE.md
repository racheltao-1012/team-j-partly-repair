# Photo Damage Analysis and Impact Propagation

## 一、这一版真正完成了什么

新流程已经接入原网站：

```text
选择车辆
→ 上传 1–4 张事故照片
→ 真实视觉 Provider 识别可见损伤
→ 将通用部位名称匹配到当前车型目录
→ 从 part_relations 查询相邻与受力路径
→ 计算隐藏零件检查概率
→ 用本次照片特征检索相似的已确认历史案例
→ 匹配候选 OEM number
→ 维修员确认、否认或修正
→ 保存 SQLite 并导出 CSV
```

页面把结果分成四层：

| 层级 | `source` | 表示什么 |
|---|---|---|
| 照片直接可见 | `visible_damage` | 模型在照片中找到的部位、损伤类型和框 |
| 撞击传播推测 | `impact_path` | 根据零件关系图建议检查，不能当作已损坏 |
| 相似案例参考 | `historical_case` | 只引用相似案例中经维修员确认的其他零件 |
| 人工输入 | `manual` | 维修员添加，或没有模型时的引导演示输入 |

车型选择框只显示年份、品牌和车型。车型只负责提供车辆身份和 OEM
目录，不再携带固定损伤。旧的 vehicle-only prediction 接口会拒绝请求；
所有正式分析都必须上传本次事故照片。

## 二、照片识别的两种 Provider

### 1. OpenAI Vision Provider

配置 `OPENAI_API_KEY` 后，网站通过 Responses API 发送 1–4 张图片，并要求
严格结构化输出：

```json
{
  "impact_zone": "front_left",
  "impact_direction": "unknown",
  "impact_severity": 0.72,
  "detections": [
    {
      "image_index": 0,
      "part_name": "front bumper cover",
      "damage_type": "deformation",
      "confidence": 0.88,
      "severity": 0.70,
      "bounding_box": {
        "x1": 0.18,
        "y1": 0.43,
        "x2": 0.81,
        "y2": 0.89
      },
      "visual_evidence": "Visible distortion along the bumper surface"
    }
  ]
}
```

这个 Provider 是真实的图像推理，但输出的是保守方框，不是像素级 mask。
官方图像输入与 Structured Outputs 文档：

- https://developers.openai.com/api/docs/guides/images-vision
- https://developers.openai.com/api/docs/guides/structured-outputs

### 2. Segmentation Webhook Provider

如果团队训练了 YOLO、Mask R-CNN、SAM 或其他专门模型，将：

```text
VISION_PROVIDER=webhook
VISION_WEBHOOK_URL=https://你们的模型服务/analyse
```

网站会把经过清理的图片以 Base64 JSON 发送给该服务。服务必须返回与上面
相同的 `VisionResult` 结构。这样可替换模型而不修改数据库、传播服务或
前端。

当前统一结构使用 bounding box。若正式加入 mask，可在 Provider 返回中增加
`mask_rle` 或 polygon，并在前端叠加；撞击传播只需要标准化后的受损部位和
严重度，不依赖 mask 的存储格式。

## 三、没有模型密钥时为什么仍能演示

网站会自动进入：

```text
Guided demo — not image inference
```

维修员输入可见部位、损伤类型、严重度和撞击区域，系统从该人工种子继续执行：

```text
OEM 匹配 → 撞击传播 → 隐藏检查 → 保存与导出
```

这个模式只用于展示后半段工作流，页面和数据库都会标记
`technician_guided_demo`，不会冒充照片 AI。

## 四、OEM 匹配如何执行

视觉模型只输出：

```text
front bumper cover
```

`app/part_matching.py` 会：

1. 统一大小写、空格和标点。
2. 把 `front fascia`、`front bumper` 等别名映射到统一部位。
3. 与当前车辆的 Partly 或本地目录计算词语重合和名称相似度。
4. 达到阈值才填写 `part_id` 与 `oem_number`。
5. 匹配不足时保留通用名称，不编造 OEM。

因此：

```text
照片 → 通用部位
车型目录 → OEM 候选
维修员 → 最终确认
```

## 五、撞击传播公式

传播图保存在 SQLite 的 `part_relations` 表。默认关系包括：

```text
Front bumper cover
→ Energy absorber
→ Bumper reinforcement
→ Crash box
→ Front rail
```

每条边包含：

```text
source_part
target_part
relation_type
propagation_weight
impact_zone
```

对一条经过 `h` 层的路径，代码计算：

\[
p_{\text{path}}
= c_{\text{visible}}
\times (0.45 + 0.55s)
\times \prod_{k=1}^{h}
\left(w_k d_k e^{-0.18(k-1)}\right)
\]

其中：

- \(c_{\text{visible}}\)：可见损伤置信度；
- \(s\)：照片估计的严重度；
- \(w_k\)：第 \(k\) 条零件关系边的传播权重；
- \(d_k\)：撞击区域与该边方向的一致系数；
- 指数项让更远的路径逐层衰减。

多个可见部位都指向同一隐藏零件时，使用：

\[
p_{\text{combined}}=1-\prod_i(1-p_i)
\]

输出等级：

| 概率 | 页面等级 |
|---:|---|
| `≥ 0.50` | high |
| `0.25–0.49` | medium |
| `< 0.25` | low |

这些数字是检查排序，不是物理碰撞仿真的损坏概率。真正上线前必须用维修历史
校准边权重和阈值。

## 六、数据保存

新增表：

| 表 | 内容 |
|---|---|
| `photo_assessments` | 模型、撞击区域、严重度、完整结构化结果 |
| `assessment_images` | 图片 ID、受控路径、类型、大小和顺序 |
| `part_relations` | 可审计的零件连接与传播权重 |

`cases.photo_run_id` 将最终维修案例关联到照片分析。`case_items` 额外保存：

- `damage_type`
- `severity`
- `evidence_image_id`
- `evidence_box`
- `reason`
- `propagation_path`
- `probability_band`

## 七、相似历史案例怎样参与

历史案例不会因为“车型相同”就自动出现。系统先从本次照片分析取得：

```text
impact_zone
visible part
damage_type
impact_severity
```

再与同一车辆目录下、已经由维修员保存的照片案例比较。相似度权重为：

| 特征 | 权重 |
|---|---:|
| 撞击区域 | 35% |
| 可见受损零件 | 40% |
| 损伤类型 | 10% |
| 严重度接近程度 | 15% |

相似度低于 `55%` 时不返回历史建议。即使严重度接近，如果撞击区域和可见
零件都不相似，分数会直接归零。通过阈值后，也只读取：

```text
technician_decision = Confirm
```

的其他零件，并标记为：

```text
Similar-case check — recommended for inspection
```

这代表“过去相似案例中确认过，建议本次检查”，不代表照片已经识别出该零件
损坏。

## 八、接口

| 接口 | 作用 |
|---|---|
| `GET /api/v1/photo-assessments/status` | 查看真实模型是否配置 |
| `POST /api/v1/photo-assessments/analyse` | 上传照片并运行完整链路 |
| `GET /api/v1/photo-assessments/{run_id}` | 读取已保存分析 |
| `GET /api/v1/photo-assessments/{run_id}/images/{image_id}` | 受控读取照片 |
| `GET /api/v1/part-relations` | 查看传播图和权重 |

## 九、答辩时应当怎样表述

建议使用：

> We detect directly visible damage from multiple vehicle photos, resolve the
> affected exterior component against a vehicle-specific catalogue, then use an
> auditable part-dependency graph and similarity-gated technician-confirmed
> cases to rank additional components for inspection. Suggested parts are not
> presented as photo-confirmed damage.

不要声称：

```text
一张照片可以准确确认全部内部损坏和最终 OEM number。
```

当前可信边界是：

```text
照片识别可见证据
+ 图模型排序隐藏检查
+ 车型目录提供 OEM 候选
+ 维修员给出最终确认
```
