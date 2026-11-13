"""Character-level reading analysis, independent of HTTP and HTML."""

from collections import Counter

from .chinese_text import is_han_character

COMMON_SURNAMES = set(
    "李王张劉刘陈陳杨楊黄黃赵趙吴吳周徐孙孫马馬朱胡郭何高林罗羅郑鄭梁谢謝宋唐许許韩韓冯馮邓鄧曹彭曾肖田董袁潘于余蒋蔣蔡杜叶葉程苏蘇魏吕呂丁任沈姚卢盧姜崔钟鍾谭譚陆陸汪范金石廖贾賈夏韦韋付方白邹鄒孟熊秦邱江尹薛闫閻段雷侯龙龍史陶黎贺賀顾顧毛郝龚龔邵万萬钱錢严嚴覃武戴莫孔向汤湯"
)


def likely_name_candidates(text):
    """Suggest surname + one/two-character name patterns with source context."""
    chars = list(text)
    candidates = {}
    for index, surname in enumerate(chars):
        if surname not in COMMON_SURNAMES or (index and is_han_character(chars[index - 1])):
            continue
        following = []
        for char in chars[index + 1:index + 3]:
            if not is_han_character(char):
                break
            following.append(char)
        if not following:
            continue
        name = surname + "".join(following)
        context = "".join(chars[max(0, index - 8):min(len(chars), index + len(following) + 9)])
        candidates.setdefault(name, context)
    return [{"name": name, "context": context} for name, context in sorted(candidates.items())]


def analyze_reading(text, character_statuses):
    """Return character counts, coverage, candidates, and render-ready spans."""
    counts = Counter(char for char in text if is_han_character(char))
    occurrence_count = sum(counts.values())
    tracked_count = sum(count for char, count in counts.items() if char in character_statuses)
    known_count = sum(
        count for char, count in counts.items() if character_statuses.get(char) == "known"
    )

    spans = []
    for char in text:
        status = None
        if is_han_character(char):
            learning_status = character_statuses.get(char)
            status = "known" if learning_status == "known" else "tracked" if learning_status else "unknown"
        if spans and spans[-1][1] == status:
            spans[-1] = (spans[-1][0] + char, status)
        else:
            spans.append((char, status))

    return {
        "text": text,
        "occurrences": occurrence_count,
        "distinct_count": len(counts),
        "known_occurrences": known_count,
        "tracked_occurrences": tracked_count,
        "unknown": [{"character": char, "count": counts[char]} for char in sorted(counts) if char not in character_statuses],
        "candidates": likely_name_candidates(text),
        "spans": spans,
    }
