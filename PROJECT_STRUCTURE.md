# Xiaomi Miloco 项目结构文档

## 项目概述

**Xiaomi Miloco (Xiaomi Local Copilot)** 是一个智能家居未来探索方案，以米家摄像机为视觉信息来源，以自研大模型为核心，打通全屋 IoT 设备。基于大模型的开发范式，让用户能够以自然语言定义家庭的各种需求和规则。

## 项目目录结构

### 根目录

- **assets/**: 静态资源文件（图片、文档等）
- **config/**: 配置文件目录
  - `ai_engine_config.yaml`: AI引擎配置
  - `prompt_config.yaml`: 提示词配置
  - `server_config.yaml`: 服务器配置
- **docker/**: Docker相关文件
- **docs/**: 文档目录
- **miloco_ai_engine/**: AI引擎服务（LLM模型管理）
- **miloco_server/**: 主服务器（业务逻辑）
- **miot_kit/**: 米家设备SDK
- **scripts/**: 脚本文件
- **third_party/**: 第三方库（llama.cpp等）
- **web_ui/**: 前端界面

---

## miloco_server/ - 主服务器

### agent/ - 智能代理模块
处理用户请求的智能代理，负责任务分解和执行。

- **chat_agent.py**
  - `ChatAgent`: 聊天代理（Actor模式），实现ReAct（Think-Act-Observe）循环
    - `__init__()`: 初始化代理，设置LLM代理、工具执行器等
    - `receiveMessage()`: 接收消息（Actor消息处理入口）
    - `_run_chat()`: 运行聊天主流程
    - `_cyclic_execute()`: 循环执行（ReAct循环）
    - `_execute_step()`: 执行单步（思考->行动->观察）
    - `_call_llm_stream()`: 调用LLM流式接口
    - `_process_llm_chunk()`: 处理LLM流式响应块
    - `_execute_tools()`: 执行工具调用
    - `_execute_single_tool()`: 执行单个工具
    - `_post_process_tool_call()`: 后处理工具调用结果
    - `_has_tool_calls()`: 检查是否有工具调用
    - `_merge_delta_tool_calls()`: 合并增量工具调用
    - `_set_tools_meta()`: 设置工具元数据（MCP工具列表）
    - `_init_conversation()`: 初始化对话历史
    - `_get_system_prompt()`: 获取系统提示词
    - `_handle_event()`: 处理事件
    - `_parse_and_handle_event()`: 解析并处理事件
    - `_run_finally_do()`: 最终处理（成功/失败）
    - `_send_instruction()`: 发送指令消息
    - `_send_dialog_finish()`: 发送对话完成消息
    - `_is_completion_step()`: 检查是否为完成步骤
    - `_handle_exit_request()`: 处理退出请求

- **dynamic_execute_agent.py**
  - `DynamicExecuteAgent`: 动态执行代理，处理动态规则执行
    - `execute_dynamic_action()`: 执行动态动作

- **nlp_request_agent.py**
  - `NLPRequestAgent`: NLP请求代理，处理自然语言请求
    - `process_request()`: 处理NLP请求

### config/ - 配置模块
加载和管理系统配置。

- **config_loader.py**
  - `load_config()`: 加载配置文件
  - `get_config()`: 获取配置值

- **normal_config.py**
  - 定义常规配置常量（数据库路径、静态文件路径等）

- **prompt_config.py**
  - `load_prompt_config()`: 加载提示词配置

### controller/ - 控制器层（API路由）
FastAPI路由处理器，处理HTTP请求。

- **auth_controller.py**
  - `login()`: 用户登录
  - `logout()`: 用户登出
  - `get_user_info()`: 获取用户信息
  - `set_user_language()`: 设置用户语言

- **chat_controller.py**
  - `ws_query()`: WebSocket聊天查询
  - `get_chat_history()`: 获取聊天历史
  - `list_chat_histories()`: 列出聊天历史列表
  - `delete_chat_history()`: 删除聊天历史
  - `search_chat_histories()`: 搜索聊天历史

- **ha_controller.py** - Home Assistant控制器
  - `set_ha_config()`: 设置HA配置
  - `get_ha_config()`: 获取HA配置
  - `get_ha_automations()`: 获取HA自动化列表
  - `get_ha_automation_actions()`: 获取HA自动化动作
  - `refresh_ha_automations()`: 刷新HA自动化
  - `refresh_ha_cameras()`: 刷新HA摄像头
  - `get_ha_camera_image()`: 获取HA摄像头图片
  - `get_ha_camera_hls_stream_url()`: 获取HLS流URL
  - `proxy_ha_hls_stream()`: 代理HLS流
  - `proxy_ha_hls_segment()`: 代理HLS片段

- **mcp_controller.py** - MCP服务控制器
  - `list_mcp_servers()`: 列出MCP服务器
  - `create_mcp_server()`: 创建MCP服务器配置
  - `update_mcp_server()`: 更新MCP服务器配置
  - `delete_mcp_server()`: 删除MCP服务器配置
  - `test_mcp_connection()`: 测试MCP连接

- **miot_controller.py** - 米家设备控制器
  - `xiaomi_home_callback()`: 小米账号OAuth回调
  - `get_miot_login_status()`: 获取登录状态
  - `get_miot_user_info()`: 获取用户信息
  - `get_miot_camera_list()`: 获取摄像头列表
  - `get_miot_device_list()`: 获取设备列表
  - `refresh_miot_all_info()`: 刷新所有信息
  - `refresh_miot_cameras()`: 刷新摄像头
  - `refresh_miot_scenes()`: 刷新场景
  - `get_miot_scene_actions()`: 获取场景动作
  - `send_notify()`: 发送通知
  - `MIoTVideoStreamManager`: 视频流管理器
  - `video_stream_websocket()`: 视频流WebSocket

- **model_controller.py** - 模型管理控制器
  - `list_models()`: 列出模型
  - `load_model()`: 加载模型
  - `unload_model()`: 卸载模型
  - `get_model_info()`: 获取模型信息

- **trigger_controller.py** - 触发规则控制器
  - `create_trigger_rule()`: 创建触发规则
  - `update_trigger_rule()`: 更新触发规则
  - `delete_trigger_rule()`: 删除触发规则
  - `get_trigger_rule()`: 获取触发规则
  - `list_trigger_rules()`: 列出触发规则
  - `get_trigger_rule_logs()`: 获取触发规则日志

- **web_controller.py** - Web界面控制器
  - 提供静态文件服务

- **main.py** - 应用入口
  - `app`: FastAPI应用实例
  - `catch_all_exceptions_middleware()`: 全局异常处理中间件
  - `startup()`: 启动逻辑
  - `shutdown()`: 关闭逻辑

### dao/ - 数据访问层
数据库操作封装。

- **chat_history_dao.py**
  - `ChatHistoryDAO`: 聊天历史数据访问
    - `create_chat_history()`: 创建聊天历史
    - `get_chat_history()`: 获取聊天历史
    - `list_chat_histories()`: 列出聊天历史
    - `delete_chat_history()`: 删除聊天历史
    - `search_chat_histories()`: 搜索聊天历史

- **kv_dao.py** - 键值对数据访问
  - `KVDao`: 键值对存储
    - `get()`: 获取值
    - `set()`: 设置值
    - `delete()`: 删除值
  - `AuthConfigKeys`: 认证配置键
  - `SystemConfigKeys`: 系统配置键
  - `DeviceInfoKeys`: 设备信息键

- **mcp_config_dao.py** - MCP配置数据访问
  - `MCPConfigDAO`: MCP配置数据访问
    - `create_mcp_config()`: 创建MCP配置
    - `get_mcp_config()`: 获取MCP配置
    - `list_mcp_configs()`: 列出MCP配置
    - `update_mcp_config()`: 更新MCP配置
    - `delete_mcp_config()`: 删除MCP配置

- **third_party_model_dao.py** - 第三方模型数据访问
  - `ThirdPartyModelDAO`: 第三方模型数据访问
    - `create_model()`: 创建模型记录
    - `get_model()`: 获取模型
    - `list_models()`: 列出模型
    - `update_model()`: 更新模型
    - `delete_model()`: 删除模型

- **trigger_dao.py** - 触发规则数据访问
  - `TriggerRuleDAO`: 触发规则数据访问
    - `create_trigger_rule()`: 创建触发规则
    - `get_trigger_rule()`: 获取触发规则
    - `list_trigger_rules()`: 列出触发规则
    - `update_trigger_rule()`: 更新触发规则
    - `delete_trigger_rule()`: 删除触发规则

- **trigger_rule_log_dao.py** - 触发规则日志数据访问
  - `TriggerRuleLogDAO`: 触发规则日志数据访问
    - `create_trigger_rule_log()`: 创建日志
    - `get_trigger_rule_log()`: 获取日志
    - `list_trigger_rule_logs()`: 列出日志
    - `delete_trigger_rule_log()`: 删除日志

### mcp/ - MCP (Model Context Protocol) 模块
MCP客户端管理，用于与外部MCP服务器通信。

- **mcp_client.py**
  - `MCPClient`: MCP客户端
    - `connect()`: 连接MCP服务器
    - `disconnect()`: 断开连接
    - `call_tool()`: 调用工具
    - `list_tools()`: 列出可用工具

- **mcp_client_manager.py**
  - `MCPClientManager`: MCP客户端管理器
    - `create()`: 创建管理器实例
    - `get_client()`: 获取客户端
    - `add_client()`: 添加客户端
    - `remove_client()`: 移除客户端
    - `list_clients()`: 列出所有客户端

- **local_mcp_servers.py**
  - 定义本地MCP服务器配置

- **tool_executor.py**
  - `ToolExecutor`: 工具执行器
    - `execute_tool()`: 执行工具
    - `execute_mcp_action()`: 执行MCP动作

### middleware/ - 中间件
请求处理中间件。

- **auth_middleware.py**
  - `verify_token()`: 验证Token
  - `AuthStaticFiles`: 带认证的静态文件服务

- **exception_handler.py**
  - `handle_exception()`: 处理异常
  - `ExceptionHandler`: 异常处理器

- **exceptions.py**
  - 定义自定义异常类
    - `ValidationException`: 验证异常
    - `AuthenticationException`: 认证异常
    - `NotFoundException`: 未找到异常

### proxy/ - 代理层
与外部服务通信的代理。

- **ha_proxy.py** - Home Assistant代理
  - `HAProxy`: HA服务代理，处理与Home Assistant的通信
    - `__init__()`: 初始化代理（KV存储）
    - `init_ha_info_dict()`: 初始化HA信息字典（从KV存储加载配置）
    - `set_ha_config()`: 设置HA配置（base_url, token）并验证
    - `get_ha_config()`: 获取HA配置
    - `refresh_ha_automations()`: 刷新HA自动化列表
    - `refresh_cameras()`: 刷新HA摄像头列表
    - `get_ha_cameras()`: 获取HA摄像头信息列表
    - `get_automations()`: 获取自动化信息字典
    - `get_camera_snapshot()`: 获取摄像头快照（多种方法尝试）
    - `get_recent_camera_img()`: 获取最近摄像头图片序列
    - `call_automation()`: 调用HA自动化
    - `get_camera_hls_stream_url()`: 获取摄像头HLS流URL
    - `_fetch_and_save_automations()`: 获取并保存自动化信息
    - `_fetch_and_save_cameras()`: 获取并保存摄像头信息

- **llm_proxy.py** - LLM代理
  - `LLMProxy`: LLM服务代理抽象基类
    - `async_call_llm()`: 异步调用LLM（非流式）
    - `async_call_llm_stream()`: 异步调用LLM（流式）
    - `_handle_async_stream_response()`: 处理异步流式响应
    - `_handle_async_stream_error()`: 处理异步流式错误
  - `OpenAIProxy`: OpenAI兼容的LLM代理实现
    - `__init__()`: 初始化代理（base_url, api_key, model_name）
    - `async_call_llm()`: 调用OpenAI兼容API（非流式）
    - `async_call_llm_stream()`: 调用OpenAI兼容API（流式）

- **miot_proxy.py** - 米家设备代理
  - `MiotProxy`: 米家设备代理，处理与米家设备的通信
    - `__init__()`: 初始化代理（UUID、重定向URI、KV存储等）
    - `create_miot_proxy()`: 类方法，创建并初始化代理实例
    - `init_miot_info()`: 初始化米家信息（OAuth、Token刷新等）
    - `refresh_miot_info()`: 刷新所有米家信息（摄像头、场景、用户、设备）
    - `refresh_cameras()`: 刷新摄像头列表
    - `refresh_scenes()`: 刷新场景列表
    - `refresh_user_info()`: 刷新用户信息
    - `refresh_devices()`: 刷新设备列表
    - `get_cameras()`: 获取摄像头信息字典
    - `get_camera_dids()`: 获取摄像头设备ID列表
    - `get_recent_camera_img()`: 获取最近摄像头图片序列
    - `get_devices()`: 获取设备信息字典
    - `get_scenes()`: 获取场景信息字典
    - `execute_scene()`: 执行场景
    - `send_notify()`: 发送米家通知
    - `get_user_info()`: 获取用户信息
    - `_check_and_refresh_token()`: 检查并刷新Token
    - `_start_token_refresh_task()`: 启动Token刷新任务
    - `init_miot_info_dict()`: 初始化米家信息字典（从KV存储加载）

### schema/ - 数据模型定义
Pydantic模型定义。

- **auth_schema.py**
  - `LoginRequest`: 登录请求
  - `LoginResponse`: 登录响应
  - `UserInfo`: 用户信息
  - `UserLanguage`: 用户语言

- **chat_schema.py**
  - `ChatMessage`: 聊天消息
  - `ChatRequest`: 聊天请求
  - `ChatResponse`: 聊天响应

- **chat_history_schema.py**
  - `ChatHistory`: 聊天历史
  - `ChatHistoryCreate`: 创建聊天历史
  - `ChatHistoryUpdate`: 更新聊天历史

- **common_schema.py**
  - 通用数据模型

- **mcp_schema.py**
  - `MCPConfig`: MCP配置
  - `MCPConfigCreate`: 创建MCP配置
  - `MCPConfigUpdate`: 更新MCP配置

- **miot_schema.py**
  - `DeviceInfo`: 设备信息
  - `CameraInfo`: 摄像头信息
  - `CameraImgInfo`: 摄像头图片信息
  - `CameraImgSeq`: 摄像头图片序列
  - `SceneInfo`: 场景信息

- **model_schema.py**
  - `ModelLoadRequest`: 模型加载请求
  - `ThirdPartyModelInfo`: 第三方模型信息
  - `LLMModelInfo`: LLM模型信息
  - `ModelsList`: 模型列表

- **trigger_schema.py**
  - `Action`: 动作
  - `TriggerRule`: 触发规则
  - `TriggerFrequencyFilter`: 触发频率过滤器
  - `TriggerFilter`: 触发过滤器

- **trigger_log_schema.py**
  - `TriggerConditionResult`: 触发条件结果
  - `ActionExecuteResult`: 动作执行结果
  - `TriggerRuleLog`: 触发规则日志

### service/ - 业务逻辑层
核心业务逻辑实现。

- **auth_service.py**
  - `AuthService`: 认证服务
    - `login()`: 用户登录
    - `logout()`: 用户登出
    - `verify_token()`: 验证Token
    - `get_user_language()`: 获取用户语言
    - `set_user_language()`: 设置用户语言

- **chat_agent_dispatcher.py**
  - `ChatAgentDispatcher`: 聊天代理分发器
    - `dispatch()`: 分发聊天请求

- **chat_history_service.py**
  - `ChatHistoryService`: 聊天历史服务
    - `create_chat_history()`: 创建聊天历史
    - `get_chat_history()`: 获取聊天历史
    - `list_chat_histories()`: 列出聊天历史
    - `delete_chat_history()`: 删除聊天历史
    - `search_chat_histories()`: 搜索聊天历史

- **ha_service.py** - Home Assistant服务
  - `HaService`: HA服务
    - `get_ha_cameras()`: 获取HA摄像头
    - `get_ha_automations()`: 获取HA自动化
    - `execute_ha_automation()`: 执行HA自动化
    - `refresh_ha_cameras()`: 刷新HA摄像头
    - `refresh_ha_automations()`: 刷新HA自动化

- **manager.py** - 服务管理器（单例）
  - `Manager`: 服务管理器，统一管理所有服务的生命周期和依赖注入
    - `__init__()`: 初始化管理器（单例模式）
    - `initialize()`: 初始化所有服务（DAO、Proxy、Service、Runner等）
    - `init_device_uuid()`: 初始化设备UUID
    - `get_llm_proxy_by_purpose()`: 根据用途获取LLM代理
    - `get_language()`: 获取用户语言
    - 属性访问器（Properties）:
      - `auth_service`: 认证服务
      - `miot_service`: 米家设备服务
      - `ha_service`: Home Assistant服务
      - `trigger_rule_service`: 触发规则服务
      - `model_service`: 模型管理服务
      - `mcp_service`: MCP服务
      - `chat_service`: 聊天历史服务
      - `chat_companion`: 聊天伴侣
      - `tool_executor`: 工具执行器
      - `default_preset_action_manager`: 默认预设动作管理器
      - `kv_dao`: KV数据访问对象
      - `trigger_rule_dao`: 触发规则数据访问对象
      - `third_party_model_dao`: 第三方模型数据访问对象
      - `mcp_config_dao`: MCP配置数据访问对象
      - `chat_history_dao`: 聊天历史数据访问对象
      - `trigger_rule_log_dao`: 触发规则日志数据访问对象
      - `cleaner`: 清理器
      - `miot_proxy`: 米家设备代理
      - `ha_proxy`: Home Assistant代理
  - `get_manager()`: 全局函数，获取管理器单例实例

- **mcp_service.py** - MCP服务
  - `McpService`: MCP服务
    - `list_mcp_servers()`: 列出MCP服务器
    - `create_mcp_server()`: 创建MCP服务器配置
    - `update_mcp_server()`: 更新MCP服务器配置
    - `delete_mcp_server()`: 删除MCP服务器配置
    - `test_mcp_connection()`: 测试MCP连接

- **miot_service.py** - 米家设备服务
  - `MiotService`: 米家设备服务
    - `get_cameras()`: 获取摄像头
    - `get_devices()`: 获取设备
    - `get_scenes()`: 获取场景
    - `execute_scene()`: 执行场景
    - `send_notify()`: 发送通知
    - `refresh_cameras()`: 刷新摄像头
    - `refresh_devices()`: 刷新设备
    - `refresh_scenes()`: 刷新场景

- **model_service.py** - 模型管理服务
  - `ModelService`: 模型管理服务
    - `list_models()`: 列出模型
    - `load_model()`: 加载模型
    - `unload_model()`: 卸载模型
    - `get_model_info()`: 获取模型信息

- **trigger_rule_dynamic_executor.py** - 触发规则动态执行器
  - `TriggerRuleDynamicExecutor`: 动态执行器（Actor模式）
    - `execute_dynamic_action()`: 执行动态动作
  - `RegisterWebSocket`: WebSocket注册

- **trigger_rule_runner.py** - 触发规则运行器
  - `TriggerRuleRunner`: 触发规则运行器，定时检查并执行触发规则
    - `__init__()`: 初始化运行器，接收规则列表、代理等依赖
    - `add_trigger_rule()`: 添加触发规则到运行列表
    - `remove_trigger_rule()`: 从运行列表移除触发规则
    - `start_periodic_task()`: 启动周期性任务（定时检查规则）
    - `stop_periodic_task()`: 停止周期性任务
    - `is_task_running()`: 检查任务是否正在运行
    - `_periodic_task()`: 周期性任务主循环
    - `_execute_scheduled_task()`: 执行定时任务（获取摄像头图片、检查运动、调用LLM）
    - `_check_trigger_condition()`: 检查触发条件（调用LLM视觉理解）
    - `_call_vision_understaning()`: 调用视觉理解LLM
    - `_check_camera_motion()`: 检查摄像头运动（基于图片差异）
    - `_execute_trigger_action()`: 执行触发动作（通知、场景、MCP等）
    - `_execute_dynamic_action()`: 执行动态动作（AI推荐的动作）
    - `execute_action()`: 执行单个动作
    - `_check_dynamic_action_is_running()`: 检查动态动作是否正在运行
    - `_log_rule_execution()`: 记录规则执行日志

- **trigger_rule_service.py** - 触发规则服务
  - `TriggerRuleService`: 触发规则服务，管理规则的CRUD操作
    - `__init__()`: 初始化服务，接收DAO、运行器等依赖
    - `create_trigger_rule()`: 创建触发规则（验证摄像头ID、通知内容等）
    - `update_trigger_rule()`: 更新触发规则（验证并更新规则）
    - `delete_trigger_rule()`: 删除触发规则
    - `get_trigger_rule()`: 获取单个触发规则详情
    - `get_all_trigger_rules()`: 获取所有触发规则列表（支持按启用状态过滤）
    - `get_trigger_rule_logs()`: 获取触发规则执行日志
    - `execute_actions()`: 执行动作列表
    - `send_dynamic_execute_log()`: 通过WebSocket发送动态执行日志
    - `make_trigger_rule_detail()`: 构建规则详情（包含设备信息等）
    - `make_trigger_rule_details()`: 批量构建规则详情
    - `_get_all_valid_camera_dids()`: 获取所有有效摄像头ID（MIoT + HA）
    - `_check_notify()`: 检查通知内容（内容过滤）
    - `_build_trigger_rule_detail()`: 构建规则详情对象

### tools/ - 工具模块
LLM可调用的工具。

- **rule_create_tool.py**
  - `RuleCreateTool`: 规则创建工具（Actor模式）
    - `create_rule()`: 创建规则

- **vision_chat_tool.py**
  - `VisionChatTool`: 视觉聊天工具（Actor模式）
    - `vision_understand()`: 视觉理解

### utils/ - 工具函数
通用工具函数和辅助类。

- **carmera_vision_handler.py** - 摄像头视觉处理器
  - `SizeLimitedQueue`: 大小限制队列
  - `CameraVisionHandler`: 摄像头视觉处理器
    - `put_camera_img()`: 添加摄像头图片
    - `get_recents_camera_img()`: 获取最近摄像头图片

- **ha_camera_vision_handler.py** - HA摄像头视觉处理器
  - `HACameraVisionHandler`: HA摄像头视觉处理器
    - `put_camera_img()`: 添加摄像头图片
    - `get_recents_camera_img()`: 获取最近摄像头图片
    - `capture_immediate_snapshot()`: 立即捕获快照

- **check_img_motion.py** - 图片运动检测
  - `CheckImgMotionByDHash`: 基于DHash的运动检测
    - `check_motion()`: 检测运动
  - `check_camera_motion()`: 检查摄像头运动

- **chat_companion.py** - 聊天伴侣
  - `ChatCompanion`: 聊天伴侣
    - `get_companion_response()`: 获取伴侣响应

- **cleaner.py** - 清理器
  - `Cleaner`: 清理器
    - `clean_old_data()`: 清理旧数据

- **database.py** - 数据库工具
  - `SQLiteConnector`: SQLite连接器
    - `execute()`: 执行SQL
    - `fetch_one()`: 获取单条记录
    - `fetch_all()`: 获取所有记录
  - `init_database()`: 初始化数据库
  - `get_db_connector()`: 获取数据库连接器

- **default_action.py** - 默认动作
  - `DefaultPresetActionManager`: 默认预设动作管理器
    - `get_default_actions()`: 获取默认动作

- **http_request_forwarding.py** - HTTP请求转发
  - `forward_request()`: 转发请求
  - `forward_get()`: 转发GET请求
  - `forward_post()`: 转发POST请求

- **llm_utils/** - LLM工具集
  - **action_converter.py**
    - `ConverterResult`: 转换结果数据类
      - `action_description`: 动作描述
      - `is_inside`: 是否在预设动作中
      - `automation_id`: 自动化ID
      - `action`: 动作对象
    - `ActionDescriptionConverter`: 动作描述转换器，将自然语言转换为动作结构
      - `__init__()`: 初始化转换器（请求ID、动作描述列表、预设动作）
      - `_get_system_prompt()`: 获取系统提示词
      - `_init_conversation()`: 初始化对话（预设动作、用户需求）
      - `run()`: 运行转换器，返回转换结果列表
      - `_make_no_matched_converter_results()`: 创建无匹配的转换结果
  - **base_llm_util.py**
    - `BaseLLMUtil`: LLM工具基类
      - `_call_llm()`: 调用LLM
  - **device_chooser.py**
    - `DeviceChooser`: 设备选择器，根据位置信息选择摄像头
      - `__init__()`: 初始化选择器（请求ID、位置、设备ID列表）
      - `_get_system_prompt()`: 获取系统提示词
      - `_init_conversation()`: 初始化对话（设备信息、位置信息）
      - `_choose_camera()`: 选择摄像头（调用LLM或直接过滤）
      - `_format_camera_info()`: 格式化摄像头信息用于日志
      - `run()`: 运行选择器，返回选中的摄像头和所有摄像头
  - **vision_understander.py**
    - `VisionUnderstander`: 视觉理解器，使用LLM分析摄像头图像
      - `__init__()`: 初始化理解器（请求ID、查询、图片序列、语言）
      - `_init_conversation()`: 初始化对话（构建视觉理解提示词）
      - `run()`: 运行理解器，返回理解结果

- **local_models.py** - 本地模型
  - `ModelPurpose`: 模型用途枚举
  - `LocalModelApi`: 本地模型API枚举
  - `LocalModels`: 本地模型管理
    - `get_model_info()`: 获取模型信息

- **mcp_util.py** - MCP工具
  - `MCPConfigConverter`: MCP配置转换器
    - `convert_to_mcp_config()`: 转换为MCP配置

- **media.py** - 媒体处理
  - `ImageManager`: 图片管理器
    - `save_image()`: 保存图片
    - `get_image()`: 获取图片

- **normal_util.py** - 常规工具
  - `get_uvicorn_log_config()`: 获取uvicorn日志配置
  - `update_localhost_cert()`: 更新本地证书
  - `bytes_to_base64()`: 字节转Base64
  - `read_last_n_lines()`: 读取最后N行
  - `extract_json_from_content()`: 从内容中提取JSON

- **prompt_helper.py** - 提示词助手
  - `TriggerRuleConditionPromptBuilder`: 触发规则条件提示词构建器
    - `build_trigger_rule_prompt()`: 构建触发规则提示词
  - `VisionUnderstandToolPromptBuilder`: 视觉理解工具提示词构建器
    - `build_vision_understand_prompt()`: 构建视觉理解提示词

- **trigger_filter.py** - 触发过滤器
  - `RuleTriggerFilter`: 规则触发过滤器，控制触发频率和条件
    - `__init__()`: 初始化过滤器（条件历史、触发历史）
    - `_default_rule_state()`: 设置默认规则状态
    - `pre_filter()`: 前置过滤
      - 检查规则是否启用
      - 检查触发周期（Cron表达式）
      - 检查触发频率（限制单位时间内触发次数）
    - `post_filter()`: 后置过滤
      - 检查状态变化（只允许状态改变时触发）
      - 检查触发间隔（避免过于频繁触发）
      - 当状态为True时，允许在间隔后重新触发（支持持续条件）
    - 常量:
      - `_CONTINUOUS_CHECK_INTERVAL`: 连续检查间隔（10秒）
      - `_TRIGGER_INTERVAL_MIN`: 最小触发间隔（10秒）

---

## miloco_ai_engine/ - AI引擎服务

### config/ - 配置模块
AI引擎配置管理。

- **config.py**
  - `APP_CONFIG`: 应用配置
  - `SERVER_CONFIG`: 服务器配置
  - `LOGGING_CONFIG`: 日志配置

- **config_loader.py**
  - `load_config()`: 加载配置

- **config_info.py**
  - 配置信息定义

- **config_optimizer.py**
  - `optimize_config()`: 优化配置

### core/ - 核心C++代码
LLM模型推理核心（C++实现）。

- **batch_scheduling/**: 批处理调度
- **cache_manager/**: 缓存管理
- **utils/**: 工具函数
- **llama-mico.cpp/h**: LLaMA-MICO核心实现

### core_python/ - Python核心接口
C++核心的Python绑定。

- **lib_manager.py**
  - `LibManager`: 库管理器
    - `load_library()`: 加载库

- **llama_mico.py**
  - `LlamaMico`: LLaMA-MICO Python接口
    - `infer()`: 推理
    - `embed()`: 嵌入

### middleware/ - 中间件
- **exception_handler.py**: 异常处理
- **exceptions.py**: 异常定义

### model_manager/ - 模型管理
- **model_manager.py**
  - `ModelManager`: 模型管理器
    - `load_model()`: 加载模型
    - `unload_model()`: 卸载模型
    - `infer()`: 推理

- **model_wrapper.py**
  - `ModelWrapper`: 模型包装器

### schema/ - 数据模型
- **actor_message.py**: Actor消息模型
- **common_schema.py**: 通用模型
- **models_schema.py**: 模型相关模型

### task_scheduler/ - 任务调度
- **model_scheduler.py**
  - `ModelScheduler`: 模型调度器
    - `schedule_task()`: 调度任务

- **scheduler_task.py**
  - `SchedulerTask`: 调度任务

### utils/ - 工具函数
- **cuda_info.py**: CUDA信息
- **image_process.py**: 图片处理
- **mico_content_util.py**: MICO内容工具
- **prompt_matcher.py**: 提示词匹配
- **utils.py**: 通用工具

### main.py - AI引擎入口
- FastAPI应用，提供模型推理API

---

## miot_kit/ - 米家设备SDK

### miot/ - 米家核心模块
- **client.py**: 米家客户端
- **cloud.py**: 云端API
- **ha_api.py**: Home Assistant API
- **camera.py**: 摄像头相关
- **lan.py**: 局域网通信
- **mcp.py**: MCP协议
- **network.py**: 网络工具
- **oauth2.py**: OAuth2认证
- **spec.py**: 设备规格
- **storage.py**: 存储
- **types.py**: 类型定义

---

## 关键工作流程

### 1. 触发规则执行流程
```
TriggerRuleRunner (定时任务)
  → 获取摄像头图片
  → 检查运动
  → 调用LLM视觉理解
  → 检查触发条件
  → RuleTriggerFilter (过滤)
  → 执行动作
  → 记录日志
```

### 2. 聊天请求流程
```
ChatController (WebSocket)
  → ChatAgentDispatcher
  → ChatAgent
  → NLPRequestAgent
  → 调用工具 (VisionChatTool, RuleCreateTool)
  → LLMProxy (调用AI引擎)
  → 返回响应
```

### 3. 设备控制流程
```
用户请求
  → ChatAgent
  → DeviceChooser (选择设备)
  → ActionConverter (转换动作)
  → MiotProxy/HAProxy (执行控制)
  → 返回结果
```

---

## 技术栈

- **后端框架**: FastAPI
- **数据库**: SQLite
- **LLM引擎**: LLaMA-MICO (C++)
- **设备协议**: MIoT, Home Assistant API, MCP
- **前端**: React (web_ui/)
- **部署**: Docker

---

## 总结

本项目采用分层架构：
- **Controller层**: 处理HTTP请求
- **Service层**: 业务逻辑
- **DAO层**: 数据访问
- **Proxy层**: 外部服务代理
- **Utils层**: 工具函数

核心功能：
1. **视觉理解**: 通过摄像头获取图像，使用LLM分析场景
2. **触发规则**: 基于视觉理解结果自动执行设备控制
3. **自然语言交互**: 用户通过对话控制设备和创建规则
4. **设备集成**: 支持米家设备和Home Assistant

