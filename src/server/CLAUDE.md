# cosound/server — rules for agents

Applies to everything under `src/server/`. These are hard rules, not preferences.

## Django templates

### 1. NEVER use `{# … #}` comments

Comment with HTML comments instead:

```html
<!-- Why this block exists. -->
```

If the note genuinely must not reach the browser, use `{% comment %} … {% endcomment %}`.
But `<!-- … -->` is the house style — see `studio/index.html`, `cotton/studio_builder.html`.

**Why this is a hard rule.** Django's lexer is line-bounded. From
`django/template/base.py`:

```python
tag_re = re.compile(r"({%.*?%}|{{.*?}}|{#.*?#})")   # note: no re.DOTALL
```

`.` does not match a newline, so **any `{# … #}` that wraps onto a second line
stops being a comment and is emitted as literal page text.** Our HTML formatter
(Prettier via Zed; djLint via VS Code) reflows prose to the print width, so a
`{# … #}` comment longer than one line is *guaranteed* to be rewrapped and
silently break. This is not hypothetical — it produced

```
TemplateSyntaxError: Invalid block tag on line 34: 'endpartialdef'
```

on `/studio/`, because the reflow also split `{% partialdef stage %}` across
lines, so the opening tag vanished into text and left its `{% endpartialdef %}`
orphaned.

`<!-- … -->` and `{% comment %}` blocks are both immune: they can wrap across as
many lines as the formatter likes and stay valid.

### 2. Keep every `{% … %}` and `{{ … }}` on ONE line

Same lexer limitation. A tag split across lines is not a tag — it renders as raw
text and desyncs every block tag after it. When a tag is too long for the line,
shorten it (shorter variable, a `{% with %}`, a template tag) rather than
wrapping it.

Never write:

```html
{% include "studio/index.html#page"
%}

{%
partialdef stage %}

{% if artist %} … {% elif
user.is_authenticated %}
```

### 3. djLint directives use the HTML comment form

`<!-- djlint:off -->` / `<!-- djlint:on -->`, placed *between* elements — never
inside an element's attribute list, where they parse as bogus attributes.

### 4. After editing a template, check it still lexes

```bash
cd src/server && uv run python -c "
import re, pathlib, sys
bad = 0
for p in pathlib.Path('src').rglob('*.html'):
    s = p.read_text(errors='replace')
    for m in re.finditer(r'{%(?![^%\n]*%})|{#', s):
        tok = s[m.start():m.start()+2]
        if tok == '{#':
            rest = s[m.start():]; end = rest.find('#}')
            if end != -1 and '\n' not in rest[:end]:
                print(f'{p}:{s[:m.start()].count(chr(10))+1}  {{# #}} comment — forbidden, use <!-- -->')
                bad += 1
                continue
        print(f'{p}:{s[:m.start()].count(chr(10))+1}  tag/comment broken across lines')
        bad += 1
sys.exit(1 if bad else 0)
"
```
