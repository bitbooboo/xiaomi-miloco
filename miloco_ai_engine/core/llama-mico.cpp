/**
 * Copyright (C) 2025 Xiaomi Corporation
 * This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
 */

#include "llama-mico.h"

#include <cstdint>
#include <cstring>

#include "batch_scheduling/batch-scheduler.h"
#include "common/chat.h"
#include "common/json-partial.h"
#include "common/log.h"
#include "llama-cparams.h"
#include "llama.h"
#include "utils/llama-memory-scheduling.h"
#include "utils/mico-config.h"
#include "utils/mico-dialog-util.h"

using json = nlohmann::ordered_json;

#define CHAT_CMP_ID_PREFIX "local-chatcmpl-"
#define DEFAULT_ERROR_SEQ_ID -1  // NOTE: error sequence id message not thread-safe

int32_t llama_mico_init(const char* config_json, void** handle) {
    ggml_time_init();
    common_params params;
    if (!config_params_parse_json(config_json, params)) {
        LOG_ERR("ERR: prase mico config\n");
        return -1;
    }
    common_init();

    LlamaMicoContext* ctx = new LlamaMicoContext(params);
    if (!ctx || !ctx->lctx || !ctx->model) {
        LOG_ERR("ERR: failed to initialize LlamaMicoContext\n");
        delete ctx;
        return -1;
    }
    *handle = ctx;

    // BatchScheduler
    BatchScheduler* bs = new BatchScheduler(ctx, 3);
    ctx->batch_scheduler = bs;

    return 0;
}

int32_t llama_mico_free(void* handle) {
    if (!handle) {
        LOG_ERR("ERR: handle is null\n");
        return -1;
    }
    LlamaMicoContext* ctx = static_cast<LlamaMicoContext*>(handle);
    if (ctx->batch_scheduler) {
        delete static_cast<BatchScheduler*>(ctx->batch_scheduler);
        ctx->batch_scheduler = nullptr;
    }
    if (ctx->memory_scheduler) {
        delete static_cast<LlamaMemoryScheduler*>(ctx->memory_scheduler);
        ctx->memory_scheduler = nullptr;
    }
    delete ctx;
    return 0;
}

int32_t llama_mico_request_prompt(void* handle, const char* request_json_str, int32_t* is_finished,
                                  const char** content) {
    LlamaMicoContext* ctx = static_cast<LlamaMicoContext*>(handle);  // 将void指针转换为LlamaMicoContext指针

    json request_json = json::parse(request_json_str);  // 解析请求JSON字符串
    // printf("request_json_str: %s\n", request_json_str);  // 调试输出（已注释）
    // ---------%%%%%-------->>>>>>>>>> 在这里进行规则判断
    MicoRequest request;  // 创建MicoRequest对象
    if (!from_json_to_request(request_json, request)) {  // 如果从JSON转换为请求对象失败
        auto& err_state = ctx->get_seq_state(DEFAULT_ERROR_SEQ_ID);  // 获取默认错误序列状态
        std::string err = "ERR: failed to parse request_json\n";  // 构建错误消息：解析请求JSON失败
        return stop_process(false /* success */, err, content, *is_finished, err_state, ctx, DEFAULT_ERROR_SEQ_ID,  // 返回失败结果
                            false /* stop */);  // 不停止处理
    }

    int32_t seq_id = ctx->set_seq_id(request.id);                       // 设置序列ID，确保seq_id在有效范围内
    if (seq_id < 0 || ctx->get_seq_state(seq_id).is_infering.load()) {  // 如果序列ID无效或该序列正在推理中（序列请求限制）
        auto& err_state = ctx->get_seq_state(DEFAULT_ERROR_SEQ_ID);  // 获取默认错误序列状态
        std::string err = "ERR: excessive concurrent requests\n";  // 构建错误消息：并发请求过多
        return stop_process(false /* success */, err, content, *is_finished, err_state, ctx, DEFAULT_ERROR_SEQ_ID,  // 返回失败结果
                            false /* stop */);  // 不停止处理
    }

    auto& state = ctx->get_seq_state(seq_id);  // 获取序列状态引用
    state.is_infering.store(true);  // 设置推理状态为true（正在推理）

    common_chat_templates_inputs tmpl_inputs;  // 创建聊天模板输入对象
    common_chat_params formatted_chat;  // 创建格式化聊天参数对象
    try {  // 尝试执行
        apply_chat_templates(formatted_chat, tmpl_inputs, ctx, request.messages, request.tools);  // 应用聊天模板（处理消息和工具）
    } catch (const std::exception& e) {  // 捕获异常
        std::string exception(e.what());  // 获取异常信息
        std::string err = "failed to parse messages, err: " + exception + "\n";  // 构建错误消息：解析消息失败
        return stop_process(false /* success */, err, content, *is_finished, state, ctx, seq_id, true /* stop */);  // 返回失败结果，停止处理
    }

    // ---------%%%%%-------->>>>>>>>>> 在这里进行模态位图准备
    if (!ready_modal_bitmaps(request.modal_prts, tmpl_inputs, ctx, state)) {  // 如果准备模态位图失败（从缓冲区初始化位图）
        std::string err = "failed to init bitmap from buf\n";  // 构建错误消息：从缓冲区初始化位图失败
        return stop_process(false /* success */, err, content, *is_finished, state, ctx, seq_id, true /* stop */);  // 返回失败结果，停止处理
    }

    // ---------%%%%%-------->>>>>>>>>> 在这里进行分词
    auto chunks = std::make_shared<mtmd::input_chunks>(mtmd_input_chunks_init());  // 创建输入块共享指针并初始化
    if (!from_input_to_token_chunks(formatted_chat, chunks, ctx, state)) {  // 如果从输入转换为token块失败（分词失败）
        std::string err = "tokenize failed, chat-cmpl-" + std::to_string(seq_id) + "\n";  // 构建错误消息：分词失败
        return stop_process(false /* success */, err, content, *is_finished, state, ctx, seq_id, true /* stop */);  // 返回失败结果，停止处理
    }

    limit_prompt_tokens(chunks, ctx->n_usage_context, state, ctx);  // 限制提示token数量（根据上下文使用量）

    /*================infer=====================*/  // ================推理=====================
    BatchScheduler* bs = static_cast<BatchScheduler*>(ctx->batch_scheduler);  // 将批量调度器指针转换为BatchScheduler类型
    bs->blocking_infer(chunks, seq_id, request.priority);  // 调用阻塞推理方法（批量调度器进行推理）
    llama_token token_id = ctx->get_seq_state(seq_id).last_token.load();  // 加载序列的最后生成的token ID

    std::string res = "";  // 初始化结果字符串为空
    if (llama_vocab_is_eog(ctx->vocab, token_id) || token_id < 0) {  // 如果token是结束标记（EOG）或token ID小于0
        return stop_process(true /* success */, res, content, *is_finished, state, ctx, seq_id, true /* stop */);  // 返回成功结果（空内容），停止处理
    }
    res = common_token_to_piece(ctx->lctx, token_id);  // 将token ID转换为文本片段
    return stop_process(true /* success */, res, content, *is_finished, state, ctx, seq_id, false /* stop */);  // 返回成功结果（包含文本内容），不停止处理
}

LLAMA_MICO_API int32_t llama_mico_request_generate(void* handle, const char* request_json_str, int32_t* is_finished,
                                                   const char** content) {
    LlamaMicoContext* ctx = static_cast<LlamaMicoContext*>(handle);

    json request_json = json::parse(request_json_str);
    // printf("request_json_str: %s\n", request_json_str);
    MicoRequest request;
    if (!from_json_to_request(request_json, request)) {
        auto& err_state = ctx->get_seq_state(DEFAULT_ERROR_SEQ_ID);
        std::string err = "ERR: failed to parse request_json\n";
        return stop_process(false /* success */, err, content, *is_finished, err_state, ctx, DEFAULT_ERROR_SEQ_ID,
                            false /* stop */);
    }

    int32_t seq_id = ctx->get_seq_id(request.id);                        // Ensure seq_id is within bounds
    if (seq_id < 0 || !ctx->get_seq_state(seq_id).is_infering.load()) {  // sequence request limit
        auto& err_state = ctx->get_seq_state(DEFAULT_ERROR_SEQ_ID);
        std::string err = "chat-cmpl-" + std::to_string(seq_id) + " is not in infering, please request prompt\n";
        return stop_process(false /* success */, err, content, *is_finished, err_state, ctx, DEFAULT_ERROR_SEQ_ID,
                            true /* stop */);
    }

    auto& state = ctx->get_seq_state(seq_id);
    if (request.stop) {
        std::string res = "";
        return stop_process(true /* success */, res, content, *is_finished, state, ctx, seq_id, true /* stop */);
    }
    // exceed max context
    if (state.n_past.load() >= ctx->n_usage_context) {
        std::string res = "";
        return stop_process(true /* success */, res, content, *is_finished, state, ctx, seq_id, true /* stop */,
                            true /* too long */);
    }

    llama_token last_token = state.last_token;
    std::vector<llama_token> tokens_text{last_token};
    mtmd_input_chunks* text_chunks = mtmd_create_text_chunks(tokens_text);
    auto chunks = std::make_shared<mtmd::input_chunks>(text_chunks);

    /*================infer=====================*/
    BatchScheduler* bs = static_cast<BatchScheduler*>(ctx->batch_scheduler);
    bs->blocking_infer(chunks, seq_id);

    llama_token token_id = ctx->get_seq_state(seq_id).last_token.load();
    if (token_id < 0) {
        std::string err = "chat-cmpl-" + std::to_string(seq_id) + " last token is invalid, please request prompt\n";
        return stop_process(false /* success */, err, content, *is_finished, state, ctx, seq_id, true /* stop */);
    }

    std::string res = "";
    if (llama_vocab_is_eog(ctx->vocab, token_id)) {
        return stop_process(true /* success */, res, content, *is_finished, state, ctx, seq_id, true /* stop */);
    }
    res = common_token_to_piece(ctx->lctx, token_id);
    return stop_process(true /* success */, res, content, *is_finished, state, ctx, seq_id, false /* stop */);
}