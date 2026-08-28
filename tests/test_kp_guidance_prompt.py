from prompts.templates import load_kp_guidance_mode_prompt, load_kp_system_prompt


def test_load_kp_guidance_mode_prompt_freeform():
    text = load_kp_guidance_mode_prompt("freeform")
    assert "key_nodes" in text
    assert "本局 KP 引导模式" in text


def test_load_kp_guidance_mode_prompt_script_guided():
    text = load_kp_guidance_mode_prompt("script_guided")
    assert "key_nodes" in text


def test_load_kp_system_prompt_includes_mode():
    text = load_kp_system_prompt("modern", kp_guidance="script_guided")
    assert "key_nodes" in text
    assert "KP" in text
