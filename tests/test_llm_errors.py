from chain.llm_errors import format_llm_user_error


def test_format_llm_connection_error():
    err = format_llm_user_error(Exception("Connection error."))
    assert "无法连接 LLM" in err
    assert "OPENAI_BASE_URL" in err or "api.xiaomimimo.com" in err
