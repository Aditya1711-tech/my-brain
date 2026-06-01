"""Pure-function @mention parser for user note text.

Usage:
    from app.services.notes.mention_parser import parse_mentions, Mention

    mentions = parse_mentions("Send @Sunita Sharma's docs to @Ravi")
    # [Mention(mention_text='@Sunita Sharma', char_offset=5),
    #  Mention(mention_text='@Ravi', char_offset=31)]
"""

from dataclasses import dataclass

# Punctuation characters that terminate a mention name
_TERMINAL: frozenset[str] = frozenset(',.:;!?)\\]}\'"')

# Common English words that should never be part of a name
_STOP_WORDS: frozenset[str] = frozenset({
    'a', 'an', 'and', 'are', 'at', 'but', 'by', 'for', 'from',
    'has', 'have', 'had', 'in', 'is', 'not', 'of', 'on', 'or',
    'that', 'the', 'these', 'this', 'those', 'to', 'was', 'were',
    'with',
})


@dataclass(frozen=True)
class Mention:
    mention_text: str  # the @Name token as it appears (including the leading @)
    char_offset: int   # character position of @ in the original text


def parse_mentions(text: str) -> list[Mention]:
    """Extract @mention tokens from note text.

    Rules:
    - @ must be at start-of-string or immediately preceded by whitespace or ([{
    - The first character of the name must be a letter or underscore
    - Name words are alphanumeric + underscore; single spaces between words are allowed
    - A stop word (and, or, the, …) ends the name without being included
    - Terminal punctuation (,.:;!?)]}'"), newline, or double-space ends the name
    - Minimum name length: 1 character after @

    Returns a list of Mention objects in order of appearance.
    """
    if not text:
        return []

    mentions: list[Mention] = []
    n = len(text)
    i = 0

    while i < n:
        if text[i] != '@':
            i += 1
            continue

        # @ must be at start or preceded by whitespace / open bracket
        if i > 0 and text[i - 1] not in ' \t\n\r([{':
            i += 1
            continue

        # First character of name must be a letter or underscore
        j = i + 1
        if j >= n or not (text[j].isalpha() or text[j] == '_'):
            i += 1
            continue

        # Consume name words
        words: list[str] = []
        pos = j

        while pos < n:
            # Read next word (alphanumeric + underscore)
            word_start = pos
            while pos < n and (text[pos].isalnum() or text[pos] == '_'):
                pos += 1
            word = text[word_start:pos]

            if not word:
                break

            # Stop before stop words (do not include them in the name)
            if word.lower() in _STOP_WORDS:
                break

            words.append(word)

            # Decide whether to continue to the next word
            if pos >= n:
                break
            c = text[pos]
            if c in _TERMINAL or c in '\n\r':
                break
            if c == ' ':
                # Continue only if the next non-space char starts a new word (letter/underscore)
                if pos + 1 < n and (text[pos + 1].isalpha() or text[pos + 1] == '_'):
                    pos += 1  # consume the space
                    continue
                break
            # Any other non-word character (e.g. @, #, digit after space) → stop
            break

        if words:
            mentions.append(Mention(
                mention_text='@' + ' '.join(words),
                char_offset=i,
            ))
            i = pos
        else:
            i += 1

    return mentions
