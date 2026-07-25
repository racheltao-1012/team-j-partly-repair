# Getting Started

这个文件夹是 **Team J 可扩展维修员核损网站**。它不会修改 Partly
官方文件；Partly 是其中一个数据源，本地新增车辆和 CSV 是另一个数据源。

## 你会同时运行两个窗口

| 窗口 | 文件夹 | 端口 | 作用 |
|---|---|---:|---|
| 第一个 VS Code | 官方 `partly-hackathon-2026` | 8420 | 提供车辆、AI预测、零件和OEM数据 |
| 第二个 VS Code | 新的 `team-j-partly-repair` | 8501 | 显示完整维修员核损网站 |

## 第一步：启动官方 API

1. 打开 Docker Desktop，等待 Docker Engine 启动。
2. 用 VS Code 打开官方的 `partly-hackathon-2026` **整个文件夹**。
3. 点击 `Terminal → New Terminal`。
4. 输入：

```powershell
docker compose up
```

5. 不要关掉这个终端。
6. 浏览器检查：

```text
http://localhost:8420/docs
```

能够打开就说明官方 API 正常。

## 第二步：启动我生成的网站

1. 解压下载的 ZIP。
2. 用另一个 VS Code 窗口打开 `team-j-partly-repair` **整个文件夹**。
3. 点击 `Terminal → New Terminal`。
4. 如果要让照片真正进入视觉模型，先在当前 PowerShell 终端设置密钥：

```powershell
$env:OPENAI_API_KEY="你的API key"
```

密钥只放在当前终端环境变量，不要写进 Python、Dockerfile 或发给别人。没有
密钥也能运行，但网站会明确显示 `Guided demo — not image inference`。

5. 输入：

```powershell
docker compose up --build
```

6. 不要点击 VS Code 上方绿色 Python 三角形。
7. 构建成功后浏览器打开：

```text
http://localhost:8501
```

## 在网站里做什么

### 流程 A：上传真实照片

1. 选择 Partly 演示车辆，或选择已经导入 OEM 目录的本地车辆。
2. 在 `PHOTO EVIDENCE` 上传 1–4 张 JPEG、PNG 或 WEBP：
   - 车辆整体；
   - 受损方向；
   - 损伤近照；
   - 第二角度。
3. 可选择 `Impact-zone hint`，不知道就保留 `Let model estimate`。
4. 点击 `Analyse photos`。
5. 页面上方显示真实照片与绿色框，这是照片直接可见的候选。
6. 表格中的 `Impact check` 是传播模型建议检查的隐藏零件，不代表已经损坏。
7. 检查 OEM number 和传播路径后，由维修员确认、否认或修改。
8. 保存并导出 CSV。

如果没有配置模型：

1. 页面会显示 `Guided demo — not image inference`。
2. 输入维修员肉眼看到的部位、损伤类型和严重度。
3. 仍然可以演示 OEM 匹配、撞击传播、维修员核验与保存。
4. 答辩时必须说明第一步来自人工输入，不是照片 AI。

### 流程 B：使用 Partly 原有的 8 辆演示车

1. 在 `Partly demo vehicles` 分组选择汽车。
2. 点击 `Run assessment`。
3. 查看 AI prediction、OEM number 和零件图。
4. 点击表格中的零件，左边会显示对应 diagram 与热点。
5. 维修员选择：
   - `Confirm`：确认；
   - `Reject`：否认，并选择原因；
   - `Needs inspection`：还要检查；
   - `Edit part`：AI零件不对，需要修改。
6. AI 漏掉零件时，点击 `+ Add missing part`。
7. 点击 `Save technician review` 保存。
8. 点击 `Export CSV` 下载报告。

### 流程 C：添加第 9 辆及更多车辆

1. 点击 `+ Add new vehicle`。
2. 输入 Make、Model、Year 和可选的 Trim、VIN。
3. 可以同时上传 OEM CSV；页面里有 `Download template`。
4. 点击 `Add vehicle and import catalogue`。
5. 新车辆会出现在 `Locally added vehicles` 分组。
6. 选择新车，点击 `Run assessment`。
7. 点击 `+ Add missing part`。
8. 在 Part name 输入框选择导入的零件，OEM number 会自动填入。
9. 维修员确认后保存并导出。

CSV 至少需要：

```csv
part_name,oem_number,category,diagram_url
Front bumper cover,52119-12A30,body,
Left headlamp,81150-02M90,lighting,
```

其中 `category` 和 `diagram_url` 可以留空。

### 流程 D：以后给本地车辆补目录

1. 选择 `Locally added vehicles` 中的车辆。
2. 在车辆功能说明下面选择新的 CSV。
3. 点击 `Import CSV`。
4. 同名且同 OEM number 的零件会更新；新零件会增加。

## 如果出现连接失败

先确认下面两个地址：

```text
http://localhost:8420/vehicles
http://localhost:8501/api/health
http://localhost:8501/api/v1/photo-assessments/status
```

- 第一个打不开：官方 Partly API 没有运行；本地车辆仍然可以使用。
- 第一个能打开但第二个显示连接失败：先在 Team J 终端按 `Ctrl+C`，再运行：

```powershell
docker compose down
docker compose up --build
```

- `photo-assessments/status` 中 `configured=false`：网站可以运行，但当前只有
  引导演示；检查当前 PowerShell 是否正确设置了 `OPENAI_API_KEY`，然后重新
  构建或启动容器。

## 停止项目

在两个终端里分别按：

```text
Ctrl+C
```

然后分别运行：

```powershell
docker compose down
```
