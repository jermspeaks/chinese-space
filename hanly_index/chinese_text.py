"""Unicode helpers for Chinese characters, radicals, and stroke forms."""


def is_han_character(char):
    if len(char) != 1:
        return False
    codepoint = ord(char)
    return any(
        start <= codepoint <= end
        for start, end in (
            (0x3400, 0x4DBF),   # CJK Extension A
            (0x4E00, 0x9FFF),   # CJK Unified Ideographs
            (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
            (0x20000, 0x2FA1F), # CJK Extensions B through F and compatibility supplement
            (0x30000, 0x323AF), # CJK Extensions G through I
            (0x2E80, 0x2EFF),   # CJK Radicals Supplement
            (0x2F00, 0x2FDF),   # Kangxi Radicals
            (0x31C0, 0x31EF),   # CJK Strokes
        )
    )


def han_characters(text):
    return [char for char in text if is_han_character(char)]
