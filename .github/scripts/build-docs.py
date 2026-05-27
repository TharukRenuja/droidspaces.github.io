import re, os, json, urllib.request

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s\u4e00-\u9fff-]', '', text)
    text = re.sub(r'[\s]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')

def fix_link(url):
    if url.endswith('.md') or '.md#' in url:
        url = url.lower().replace('.md', '.html')
    elif (url.endswith('.html') or '.html#' in url) and not url.startswith('http'):
        url = url.lower()
    return url

def inline_format(text):
    code_spans = []
    def save_code(m):
        code_spans.append(m.group(1))
        return f'\x00CODE{len(code_spans)-1}\x00'
    text = re.sub(r'`([^`]+)`', save_code, text)
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1">', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f'<a href="{fix_link(m.group(2))}" rel="noopener noreferrer">{m.group(1)}</a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
    text = re.sub(r'~~([^~]+)~~', r'<del>\1</del>', text)
    for i, cs in enumerate(code_spans):
        text = text.replace(f'\x00CODE{i}\x00', f'<code>{cs}</code>')
    return text

def normalize_hyphenated_links(item_html):
    if not re.fullmatch(r'(?:<a\b[^>]*>.*?</a>)(?:\s*-\s*<a\b[^>]*>.*?</a>)+', item_html):
        return item_html
    parts = re.findall(r'<a\b[^>]*>.*?</a>', item_html)
    return '<br>'.join(parts)

def parse_list_block(lines, i, parent_indent=0):
    if i >= len(lines):
        return '', i
    line = lines[i]
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    if re.match(r'^[-*+]\s+', stripped):
        list_tag = 'ul'
        marker_re = r'^[-*+]\s+'
    else:
        olm = re.match(r'^\d+\.\s+', stripped)
        if olm:
            list_tag = 'ol'
            marker_re = r'^\d+\.\s+'
        else:
            return '', i

    base_indent = indent
    items = []
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped == '':
            i += 1
            continue
        indent = len(line) - len(stripped)
        if indent < base_indent:
            break
        if not re.match(marker_re, stripped):
            break
        item_text = re.sub(marker_re, '', stripped)
        item_html = inline_format(item_text)
        i += 1

        nested_html_parts = []
        while i < len(lines):
            next_line = lines[i]
            stripped2 = next_line.lstrip()
            if stripped2 == '':
                i += 1
                continue
            indent2 = len(next_line) - len(stripped2)
            if indent2 <= base_indent:
                break
            if stripped2.startswith('```'):
                code_html, new_i = consume_code(lines, i)
                nested_html_parts.append(code_html)
                i = new_i
                continue
            nested_block, new_i = parse_list_block(lines, i, parent_indent=indent2)
            if nested_block:
                nested_html_parts.append(nested_block)
                i = new_i
                continue
            nested_html_parts.append(f'<p>{inline_format(stripped2)}</p>')
            i += 1

        nested_html = ''.join(nested_html_parts)
        items.append(f'<li>{item_html}{nested_html}</li>')

    return f'<{list_tag}>\n' + '\n'.join(items) + f'\n</{list_tag}>', i

def consume_code(lines, i):
    lang = lines[i].lstrip()[3:].strip()
    indent = len(lines[i]) - len(lines[i].lstrip())
    buf = []
    i += 1
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith('```'):
            i += 1
            break
        if indent > 0 and len(lines[i]) >= indent:
            buf.append(lines[i][indent:] + '\n')
        else:
            buf.append(lines[i] + '\n')
        i += 1
    return f'<div class="code-block"><button class="copy-btn" onclick="copyCode(this)"><i class="fa-regular fa-copy"></i> Copy</button><pre><code>{"".join(buf)}</code></pre></div>', i

def md_to_html(md):
    lines = md.split('\n')
    html = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.lstrip().startswith('```'):
            code_html, i = consume_code(lines, i)
            html.append(code_html)
            continue
        if re.match(r'^[-*_]{3,}\s*$', line):
            html.append('<hr>')
            i += 1
            continue

        # Inline anchor tag before heading
        am = re.match(r'^<a\s+id="([^"]+)"\s*/?>\s*</a>\s*$', line.strip())
        if am:
            aid = am.group(1)
            i += 1
            if i < len(lines) and re.match(r'^(#{1,6})\s+', lines[i]):
                hm = re.match(r'^(#{1,6})\s+(.+)$', lines[i])
                level = len(hm.group(1))
                text = inline_format(hm.group(2))
                html.append(f'<h{level} id="{aid}">{text}</h{level}>')
                i += 1
                continue
            else:
                html.append(f'<a id="{aid}"></a>')
                continue

        # Headings
        hm = re.match(r'^(#{1,6})\s+(.+)$', line)
        if hm:
            level = len(hm.group(1))
            text = hm.group(2)
            ain = re.search(r'<a\s+id="([^"]+)"\s*/?>\s*</a>\s*', text)
            if ain:
                aid = ain.group(1)
                text = re.sub(r'<a\s+id="[^"]+"\s*/?>\s*</a>\s*', '', text).strip()
            else:
                aid = slugify(text)
            html.append(f'<h{level} id="{aid}">{inline_format(text)}</h{level}>')
            i += 1
            continue

        # GFM Alerts
        al = re.match(r'>\s*\[!(\w+)\]\s*$', line)
        if al:
            atype = al.group(1).upper()
            i += 1
            qlines = []
            while i < len(lines):
                ql = lines[i]
                if ql.startswith('> '):
                    qlines.append(ql[2:].strip())
                    i += 1
                elif ql.strip() == '>':
                    i += 1
                else:
                    break
            content = '\n'.join(qlines)
            content = inline_format(content)
            html.append(f'<div class="callout callout-{atype.lower()}"><strong class="callout-title">{atype}</strong> {content}</div>')
            continue

        # Multi-line blockquote
        if line.startswith('> ') and not re.match(r'>\s*\[!\w+\]', line):
            qlines = []
            while i < len(lines) and (lines[i].startswith('> ') or lines[i].strip() == '>'):
                if lines[i].strip() == '>':
                    i += 1
                    continue
                qlines.append(lines[i][2:].strip())
                i += 1
            content = ' '.join(qlines)
            content = inline_format(content)
            html.append(f'<blockquote><p>{content}</p></blockquote>')
            continue

        # Tables
        if '|' in line and line.strip().startswith('|'):
            rows = []
            while i < len(lines) and '|' in lines[i] and lines[i].strip().startswith('|'):
                rows.append(lines[i])
                i += 1
            html.append(convert_table(rows))
            continue

        # Ordered lists
        if re.match(r'^\s*\d+\.\s+', line):
            list_html, i = parse_list_block(lines, i)
            html.append(list_html)
            continue

        # Unordered lists
        if re.match(r'^[\s]*[-*+]\s+', line):
            list_html, i = parse_list_block(lines, i)
            html.append(list_html)
            continue

        # Paragraph
        para = []
        while i < len(lines) and lines[i].strip():
            if lines[i].lstrip().startswith('```'):
                break
            text = inline_format(lines[i].rstrip())
            if lines[i].endswith('  '):
                text += '<br>'
            para.append(text)
            i += 1
        if para:
            html.append(f'<p>{" ".join(para)}</p>')
        if i < len(lines) and lines[i].lstrip().startswith('```'):
            code_html, i = consume_code(lines, i)
            html.append(code_html)
    return '\n'.join(html)

def convert_table(rows):
    if len(rows) < 2:
        return ''
    header = rows[0]
    data = rows[2:]
    cols = [c.strip() for c in header.split('|')]
    if cols and not cols[0]: cols = cols[1:]
    if cols and not cols[-1]: cols = cols[:-1]
    html_s = '<div class="table-wrap"><table>\n<thead>\n<tr>'
    for c in cols:
        html_s += f'<th>{inline_format(c)}</th>'
    html_s += '</tr>\n</thead>\n<tbody>\n'
    for row in data:
        cells = [c.strip() for c in row.split('|')]
        if cells and not cells[0]: cells = cells[1:]
        if cells and not cells[-1]: cells = cells[:-1]
        if not any(c for c in cells):
            continue
        html_s += '<tr>'
        for c in cells:
            html_s += f'<td>{inline_format(c)}</td>'
        html_s += '</tr>\n'
    html_s += '</tbody>\n</table></div>'
    return html_s

SECTION_ORDER = {'Basics': 0, 'Guides': 1, 'Recipes': 2, 'Reference': 3}

FALLBACK_TITLES = {
    'installation-android': 'Android Installation',
    'installation-linux': 'Linux Installation', 'features': 'Features Deep Dive',
    'gpu-acceleration': 'GPU Acceleration', 'kernel-configuration': 'Kernel Configuration',
    'usage-android-app': 'Android App Usage', 'linux-cli': 'Linux CLI Usage',
    'cool-things-you-can-do': 'Cool Things You Can Do', 'common-errors': 'Common Errors',
    'troubleshooting': 'Troubleshooting', 'community-supported-devices': 'Supported Devices',
    'nix-nixos': 'Nix / NixOS', 'uninstallation': 'Uninstallation',
}

FALLBACK_SECTIONS = {
    'installation-android': 'Basics', 'installation-linux': 'Basics',
    'features': 'Guides', 'gpu-acceleration': 'Guides', 'kernel-configuration': 'Guides',
    'usage-android-app': 'Guides', 'linux-cli': 'Guides',
    'cool-things-you-can-do': 'Recipes',
    'common-errors': 'Reference', 'troubleshooting': 'Reference',
    'community-supported-devices': 'Reference', 'nix-nixos': 'Reference', 'uninstallation': 'Reference',
}

FALLBACK_ORDER = {
    'installation-android': 1, 'installation-linux': 2,
    'features': 1, 'gpu-acceleration': 2, 'kernel-configuration': 3,
    'usage-android-app': 4, 'linux-cli': 5,
    'cool-things-you-can-do': 1,
    'troubleshooting': 1, 'common-errors': 2,
    'community-supported-devices': 3, 'nix-nixos': 4, 'uninstallation': 5,
}

FALLBACK_DESC = {
    'installation-android': 'Step-by-step Android installation guide for Droidspaces. Root your device, install the APK, set up the backend, and run Linux containers with zero terminal commands.',
    'installation-linux': 'Install Droidspaces on Linux desktop or server. Download the tarball, extract the binary, create a rootfs image, and boot your first container.',
    'features': 'Deep dive into every Droidspaces feature: namespace isolation, init system support, OverlayFS volatile mode, GPU acceleration, cgroup isolation, seccomp shields, and Android-specific tuning.',
    'gpu-acceleration': 'Enable GPU acceleration in Droidspaces containers on Android and Linux. Covers Termux-X11, VirGL, Turnip for native Adreno, and desktop GPU passthrough.',
    'kernel-configuration': 'Complete guide to compiling a custom Android kernel with Droidspaces support. Covers non-GKI and GKI kernels with kABI-safe patches.',
    'usage-android-app': 'Complete guide to the Droidspaces Android app. Manage containers, configure networking, stats, terminal, and kernel settings.',
    'linux-cli': 'Full Droidspaces Linux CLI reference. Every command, flag, and config option explained.',
    'cool-things-you-can-do': 'Cool projects with Droidspaces: secure mobile server with Tailscale + UFW + Fail2Ban, and Docker containers nested inside Droidspaces.',
    'common-errors': 'Complete collection of Droidspaces error solutions: GrapheneOS unsupported, ENOKEY, mount errors, systemd hangs, paranoid networking, and more.',
    'troubleshooting': 'Troubleshoot Droidspaces containers: systemd hangs, paranoid networking, SELinux corruption, OverlayFS f2fs, sparse image reclaim, WiFi power save.',
    'community-supported-devices': 'Community-maintained compatibility list of Android devices verified to run Droidspaces.',
    'nix-nixos': 'Run NixOS inside Droidspaces containers. Build tarballs, configure compatibility, and try the experimental Finix system.',
    'uninstallation': 'Safely uninstall Droidspaces from Android and Linux. Remove containers, backend data, APK, and system files completely.',
}

FALLBACK_KEYWORDS = {
    'installation-android': 'install Droidspaces Android, rooted Android container, APK install, atomic backend, sparse image',
    'installation-linux': 'install Droidspaces Linux, Linux container runtime, rootfs tarball, ext4 image, Linux namespaces',
    'features': 'Droidspaces features, namespace isolation, cgroup v2, OverlayFS, volatile mode, init system, GPU hardware access',
    'gpu-acceleration': 'GPU acceleration Android container, Turnip Adreno, VirGL GPU, Termux X11, llvmpipe',
    'kernel-configuration': 'kernel configuration Droidspaces, GKI kABI patches, Android kernel compile, namespace kernel config',
    'usage-android-app': 'Droidspaces Android app, container manager Android, NAT mode, built-in terminal, systemd service manager',
    'linux-cli': 'Droidspaces CLI, Linux container command line, droidspaces command reference, bind mount, NAT networking',
    'cool-things-you-can-do': 'Droidspaces mobile server, Tailscale Android container, UFW Fail2Ban container, Docker nested',
    'common-errors': 'Droidspaces common errors, ENOKEY fix, GrapheneOS, SuSFS conflict, container mount error, systemd hang',
    'troubleshooting': 'Droidspaces troubleshooting, systemd hang legacy kernel, paranoid networking, ping permission denied',
    'community-supported-devices': 'Droidspaces supported devices, Android kernel list, device compatibility, custom kernel downloads',
    'nix-nixos': 'NixOS Droidspaces, Nix container, Flake, systemd v259 legacy kernel, Finix experimental',
    'uninstallation': 'uninstall Droidspaces, remove Android container runtime, delete rootfs, remove backend files',
}

def parse_metadata(md):
    m = re.match(r'^\s*<!--\s*(.*?)-->\s*', md, re.DOTALL)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).split('\n'):
        line = line.strip()
        kv = re.match(r'(\w+):\s*(.*)', line)
        if kv:
            meta[kv.group(1).lower()] = kv.group(2).strip()
    return meta

def load_pages(docs_dir):
    pages = []
    for fname in sorted(os.listdir(docs_dir)):
        if not fname.endswith('.md'):
            continue
        slug = fname.replace('.md', '').lower()
        with open(os.path.join(docs_dir, fname)) as f:
            md = f.read()
        meta = parse_metadata(md)
        title = meta.get('title', FALLBACK_TITLES.get(slug, slug.replace('-', ' ').title()))
        section = meta.get('section', FALLBACK_SECTIONS.get(slug, 'Guides'))
        order = int(meta.get('order', FALLBACK_ORDER.get(slug, 99)))
        desc = meta.get('desc', FALLBACK_DESC.get(slug, f'Droidspaces documentation - {title}'))
        keywords = meta.get('keywords', FALLBACK_KEYWORDS.get(slug, 'Droidspaces, Linux containers, Android containers'))
        pages.append((slug, title, section, order, desc, keywords, fname))
    pages.sort(key=lambda p: (SECTION_ORDER.get(p[2], 99), p[3]))
    return pages

def sidebar(pages, slug):
    groups = {}
    for p in pages:
        groups.setdefault(p[2], []).append((p[0], p[1]))
    lines = []
    for section in ['Basics', 'Guides', 'Recipes', 'Reference']:
        if section not in groups:
            continue
        lines.append('<div class="sidebar-group">')
        lines.append(f'<div class="sidebar-heading">{section}</div>')
        for href, label in groups[section]:
            active = ' active' if href == slug else ''
            lines.append(f'<a href="{href}.html" class="sidebar-link{active}">{label}</a>')
        lines.append('</div>')
    return '\n'.join(lines)

def nav_buttons(pages, slug):
    slugs = [p[0] for p in pages]
    labels = {p[0]: p[1] for p in pages}
    try:
        idx = slugs.index(slug)
    except ValueError:
        return ''
    prev_link = next_link = ''
    if idx > 0:
        p = slugs[idx - 1]
        prev_link = f'<a href="{p}.html" class="doc-nav-btn doc-nav-prev">\u2190 {labels[p]}</a>'
    if idx < len(slugs) - 1:
        n = slugs[idx + 1]
        next_link = f'<a href="{n}.html" class="doc-nav-btn doc-nav-next">{labels[n]} \u2192</a>'
    return f'<div class="doc-nav-buttons">{prev_link}{next_link}</div>'

def breadcrumb(pages, slug):
    m = {p[0]: (p[2], p[1]) for p in pages}
    if slug not in m:
        return '<span>Docs</span>'
    section, label = m[slug]
    parts = ['<span>Docs</span>']
    if section != label:
        parts.append('<span class="bc-sep">/</span>')
        parts.append(f'<span class="bc-section">{section}</span>')
    parts.append('<span class="bc-sep">/</span>')
    parts.append(f'<span class="bc-label">{label}</span>')
    return ''.join(parts)

def make_page(title, body, slug, nav_template, footer_template, pages, is_index=False):
    s = sidebar(pages, slug)
    nav_btns = nav_buttons(pages, slug)
    bc_html = breadcrumb(pages, slug)
    seo = {}
    for p in pages:
        if p[0] == slug:
            seo = {'desc': p[4], 'keywords': p[5]}
            break
    desc = seo.get('desc', f'Droidspaces documentation - {title}')
    keywords = seo.get('keywords', 'Droidspaces, Linux containers, Android containers')

    nav_html = nav_template.replace('{{FEATURES_HREF}}', '/#features').replace('{{DOCS_STYLE}}', 'style="color:var(--accent2)"')
    footer_html = footer_template

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="{desc}">
  <meta name="keywords" content="{keywords}">
  <title>{title} - Droidspaces Docs</title>
  <meta property="og:title" content="{title} - Droidspaces Docs">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="https://www.droidspaces.org/docs/{slug}.html">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://i.ibb.co/d4PLN7Gg/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title} - Droidspaces Docs">
  <meta name="twitter:description" content="{desc}">
  <meta name="twitter:image" content="https://i.ibb.co/d4PLN7Gg/og-image.png">
  <link rel="canonical" href="https://www.droidspaces.org/docs/{slug}.html">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <link rel="icon" href="/favicon.ico">
  <link rel="apple-touch-icon" href="/favicon.ico">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
  <link rel="stylesheet" href="../style.css">
  <style>
    .docs-layout {{
      display: flex; min-height: calc(100vh - 56px);
    }}
    .sidebar {{
      width: 300px; flex-shrink: 0;
      border-right: 1px solid var(--border);
      background: var(--bg2);
      overflow-y: auto;
      position: sticky; top: 56px; height: calc(100vh - 56px);
    }}
    .sidebar-inner {{
      padding: 0;
      position: relative;
      width: 100%;
      min-width: 0;
    }}
    .sidebar-group {{
      margin-bottom: 0;
    }}
    .sidebar-heading {{
      font-family: var(--mono); font-size: 0.7rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--muted); padding: 1rem 1rem 0.25rem;
    }}
    .sidebar-link {{
      display: block; padding: 0.5rem 1rem;
      font-size: 0.9rem; color: var(--muted);
      text-decoration: none; border-radius: 0;
      transition: all 0.1s;
    }}
    .sidebar-link:hover {{
      color: var(--text); background: var(--bg3);
    }}
    .sidebar-link.active {{
      color: var(--accent2); background: rgba(79,142,247,0.08);
      font-weight: 600;
    }}
    .sidebar-content {{
      flex: 1; min-width: 0;
      padding: 2rem 2rem 4rem;
      max-width: none;
    }}
    .sidebar-content h1 {{
      font-family: var(--mono); font-size: clamp(1.5rem, 2.5vw, 2rem);
      font-weight: 700; letter-spacing: -0.03em; color: var(--text);
      margin-bottom: 1.5rem; padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border);
    }}
    .sidebar-content h2 {{
      font-family: var(--mono); font-size: 1.25rem; font-weight: 700;
      color: var(--text); margin: 2rem 0 0.75rem;
      letter-spacing: -0.02em;
    }}
    .sidebar-content h2:target {{
      border-left: 3px solid var(--accent);
      padding-left: 0.75rem;
    }}
    .sidebar-content h3 {{
      font-family: var(--mono); font-size: 1rem; font-weight: 600;
      color: var(--accent2); margin: 1.5rem 0 0.5rem;
    }}
    .sidebar-content h3:target {{
      border-left: 2px solid var(--accent);
      padding-left: 0.5rem;
    }}
    .sidebar-content p {{
      color: var(--muted); line-height: 1.7; margin-bottom: 1rem;
    }}
    .sidebar-content strong {{ color: var(--text); }}
    .sidebar-content a {{
      color: var(--accent2); text-decoration: none;
    }}
    .sidebar-content a:hover {{ text-decoration: underline; }}
    .sidebar-content code {{
      font-family: var(--mono); font-size: 0.82rem;
      background: var(--bg3); padding: 0.15rem 0.4rem;
      border-radius: 4px; color: var(--accent2);
    }}
    .sidebar-content pre {{
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: 8px; padding: 1rem; overflow-x: auto;
      margin-bottom: 1rem;
    }}
    .sidebar-content pre code {{
      background: none; padding: 0; font-size: 0.78rem;
      color: var(--text); line-height: 1.6;
    }}
    .code-block {{
      position: relative;
    }}
    .code-block:hover .copy-btn {{
      opacity: 1;
    }}
    .copy-btn {{
      position: absolute; top: 0.5rem; right: 0.5rem;
      background: var(--bg3); border: 1px solid var(--border);
      color: var(--muted); font-size: 0.7rem;
      font-family: var(--sans); padding: 0.2rem 0.5rem;
      border-radius: 4px; cursor: pointer;
      opacity: 0; transition: opacity 0.15s; z-index: 1;
      display: inline-flex; align-items: center; gap: 0.25rem;
    }}
    .copy-btn:hover {{
      color: var(--accent2); border-color: var(--accent2);
    }}
    @media (max-width: 768px) {{
      .copy-btn {{ opacity: 1; }}
      .sidebar-content a {{ word-break: break-word; }}
      .sidebar-content code {{ word-break: break-word; }}
      .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
      .sidebar-content th {{ white-space: normal; word-break: break-word; }}
      .sidebar-content td {{ word-break: break-word; }}
    }}
    .sidebar-content ul, .sidebar-content ol {{
      color: var(--muted); line-height: 1.7;
      margin-bottom: 1rem; padding-left: 1.25rem;
    }}
    .sidebar-content li {{ margin-bottom: 0.25rem; }}
    .sidebar-content li > .code-block {{ margin-top: 0.5rem; }}
    .sidebar-content blockquote {{
      border-left: 3px solid var(--accent); background: var(--bg3);
      padding: 0.75rem 1rem; margin-bottom: 1rem;
      border-radius: 0 6px 6px 0;
      color: var(--text); font-size: 0.9rem;
    }}
    .sidebar-content blockquote p {{ color: var(--text); margin-bottom: 0; }}
    .sidebar-content hr {{
      border: none; border-top: 1px solid var(--border); margin: 2rem 0;
    }}
    .table-wrap {{
      overflow-x: auto;
      margin-bottom: 1.5rem;
    }}
    .table-wrap table {{
      margin-bottom: 0;
    }}
    .sidebar-content table {{
      width: 100%; border-collapse: collapse; font-size: 0.85rem;
      margin-bottom: 1.5rem;
    }}
    .sidebar-content th {{
      font-family: var(--mono); font-size: 0.72rem; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em;
      padding: 0.75rem 1rem; text-align: left; color: var(--muted);
      border-bottom: 1px solid var(--border); background: var(--bg3);
      white-space: nowrap;
    }}
    .sidebar-content td {{
      padding: 0.75rem 1rem; border-bottom: 1px solid var(--border);
      color: var(--muted);
    }}
    .sidebar-content img {{
      max-width: 100%; border-radius: 8px; border: 1px solid var(--border);
      margin: 1rem 0;
    }}
    .sidebar-content details {{
      background: var(--bg2); border: 1px solid var(--border);
      border-radius: 8px; padding: 1rem; margin-bottom: 1rem;
    }}
    .sidebar-content summary {{
      font-family: var(--mono); font-size: 0.85rem;
      cursor: pointer; color: var(--accent2);
    }}
    .callout {{
      border-left: 4px solid var(--accent);
      background: var(--bg3); padding: 0.75rem 1rem;
      margin-bottom: 1rem; border-radius: 0 6px 6px 0;
      font-size: 0.9rem; color: var(--text);
    }}
    .callout-title {{
      font-family: var(--mono); font-size: 0.72rem;
      text-transform: uppercase; letter-spacing: 0.06em;
      display: block; margin-bottom: 0.25rem;
    }}
    .callout-note {{ border-left-color: var(--accent); }}
    .callout-note .callout-title {{ color: var(--accent); }}
    .callout-tip {{ border-left-color: var(--green); }}
    .callout-tip .callout-title {{ color: var(--green); }}
    .callout-warning {{ border-left-color: #f59e0b; }}
    .callout-warning .callout-title {{ color: #f59e0b; }}
    .callout-caution {{ border-left-color: #f59e0b; }}
    .callout-caution .callout-title {{ color: #f59e0b; }}
    .callout-important {{ border-left-color: #ef4444; }}
    .callout-important .callout-title {{ color: #ef4444; }}
    .doc-nav-buttons {{
      display: flex; justify-content: space-between; gap: 1rem;
      margin: 2rem 0 1rem;
    }}
    .doc-nav-btn {{
      padding: 0.5rem 1rem; border-radius: 8px;
      font-family: var(--sans); font-size: 0.82rem; font-weight: 500;
      text-decoration: none; color: var(--muted);
      border: 1px solid var(--border);
      transition: all 0.15s; max-width: 50%;
    }}
    .doc-nav-btn:hover {{
      color: var(--text); border-color: var(--muted);
    }}
    .doc-nav-next {{
      margin-left: auto; text-align: right;
    }}
    .doc-nav-prev {{
      text-align: left;
    }}
    .doc-copyright {{
      font-size: 0.78rem; color: var(--border2);
      padding-top: 1rem; border-top: 1px solid var(--border);
      margin-top: 1.5rem; text-align: center;
    }}
    .doc-copyright a {{
      color: var(--border2); text-decoration: none;
    }}
    .doc-copyright a:hover {{
      color: var(--muted);
    }}
    .nav-overlay {{
      display: none; position: fixed;
      top: 56px; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.5); z-index: 199;
    }}
    .nav-overlay.active {{ display: block; }}

    .sidebar-close {{
      display: none;
      position: absolute; top: 0.5rem; right: 1rem;
      background: none; border: none;
      color: var(--muted); font-size: 1.5rem;
      cursor: pointer; padding: 0.25rem 0.5rem;
      line-height: 1; border-radius: 4px;
    }}
    .sidebar-close:hover {{
      color: var(--text); background: var(--bg3);
    }}

    .doc-breadcrumb {{
      display: none;
      position: sticky;
      top: 56px;
      z-index: 50;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 1rem;
      background: var(--bg2);
      border-bottom: 1px solid var(--border);
      font-size: 0.78rem;
      color: var(--muted);
      user-select: none;
      cursor: pointer;
    }}
    .doc-breadcrumb .bc-sep {{
      color: var(--border2);
    }}
    .doc-breadcrumb .bc-section {{
      color: var(--text);
    }}
    .doc-breadcrumb .bc-label {{
      color: var(--accent2);
    }}
    @media (max-width: 768px) {{
      .sidebar {{
        display: flex;
        position: fixed; top: 56px; left: 0;
        width: 300px; height: calc(100dvh - 56px); z-index: 200;
        border-right: 1px solid var(--border);
        transform: translateX(-100%);
        transition: transform 0.25s ease;
        box-shadow: 4px 0 12px rgba(0,0,0,0.2);
      }}
      .sidebar.open {{ transform: translateX(0); }}
      .sidebar-close {{ display: block; }}
      .sidebar-content {{ padding: 1.5rem 1rem 3rem; }}
      .doc-breadcrumb {{ display: flex; }}
      .docs-layout {{ flex-direction: column; }}
      .sidebar-content th,
      .sidebar-content td {{
        padding: 0.5rem 0.5rem;
        font-size: 0.78rem;
      }}
      .sidebar-content a {{ word-break: break-word; }}
      .sidebar-content code {{ word-break: break-word; }}
      .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
      .sidebar-content th {{ white-space: normal; word-break: break-word; }}
      .sidebar-content td {{ word-break: break-word; }}
    }}
  </style>
  <script>
    (function () {{
      const savedTheme = localStorage.getItem('theme');
      if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
    }})();
  </script>
</head>
<body>
  {nav_html}
  <div class="nav-overlay" id="sidebar-overlay"></div>

  <div class="doc-breadcrumb" id="sidebar-toggle" role="button" tabindex="0" aria-label="Toggle docs navigation">
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0">
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <line x1="9" y1="3" x2="9" y2="21"/>
    </svg>
    {bc_html}
  </div>

  <div class="docs-layout">
    <aside class="sidebar" id="sidebar">
      <div class="sidebar-inner">
        <button class="sidebar-close" id="sidebar-close" aria-label="Close sidebar">&times;</button>
{s}
      </div>
    </aside>
    <div class="sidebar-content">
{body}
{nav_btns}
      <p class="doc-copyright">{footer_html}</p>
    </div>
  </div>

  <script>
    (() => {{
      const themeToggle = document.getElementById('theme-toggle');
      const sunIcon = themeToggle.querySelector('.sun-icon');
      const moonIcon = themeToggle.querySelector('.moon-icon');
      const mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
      function updateIcons(theme) {{
        sunIcon.style.display = theme === 'light' ? 'none' : 'block';
        moonIcon.style.display = theme === 'light' ? 'block' : 'none';
      }}
      function getEffectiveTheme() {{
        const saved = localStorage.getItem('theme');
        if (saved) return saved;
        return mediaQuery.matches ? 'light' : 'dark';
      }}
      function applyTheme(theme) {{
        if (theme === 'system') {{
          document.documentElement.removeAttribute('data-theme');
          updateIcons(mediaQuery.matches ? 'light' : 'dark');
        }} else {{
          document.documentElement.setAttribute('data-theme', theme);
          updateIcons(theme);
        }}
      }}
      applyTheme(getEffectiveTheme());
      mediaQuery.addEventListener('change', (e) => {{
        if (!localStorage.getItem('theme')) applyTheme(e.matches ? 'light' : 'dark');
      }});
      themeToggle.addEventListener('click', () => {{
        const currentTheme = getEffectiveTheme();
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('theme', newTheme);
        applyTheme(newTheme);
      }});
      // Docs sidebar toggle
      const sidebarToggle = document.getElementById('sidebar-toggle');
      const sidebar = document.getElementById('sidebar');
      const sidebarOverlay = document.getElementById('sidebar-overlay');

      function openSidebar() {{
        sidebar.classList.add('open');
        sidebarOverlay.classList.add('active');
        document.body.style.overflow = 'hidden';
      }}

      function closeSidebar() {{
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('active');
        document.body.style.overflow = '';
      }}

      if (sidebarToggle) {{
        sidebarToggle.addEventListener('click', (e) => {{
          e.stopPropagation();
          if (sidebar.classList.contains('open')) closeSidebar();
          else openSidebar();
        }});
      }}

      if (sidebarOverlay) {{
        sidebarOverlay.addEventListener('click', closeSidebar);
      }}

      const sidebarClose = document.getElementById('sidebar-close');
      if (sidebarClose) {{
        sidebarClose.addEventListener('click', closeSidebar);
      }}

      if (sidebar) {{
        sidebar.querySelectorAll('a').forEach(link => {{
          link.addEventListener('click', closeSidebar);
        }});
      }}
    }})();
    function copyCode(btn) {{
      const code = btn.parentElement.querySelector('pre code');
      const text = code.textContent;
      navigator.clipboard.writeText(text).then(() => {{
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        setTimeout(() => {{ btn.innerHTML = orig; }}, 1500);
      }}).catch(() => {{}});
    }}
  </script>
</body>
</html>'''

def fix_img_paths(html):
    return re.sub(r'Documentation/resources/', r'assets/resources/', html)

def fetch_latest_release():
    try:
        url = 'https://api.github.com/repos/ravindu644/Droidspaces-OSS/releases?per_page=5'
        req = urllib.request.Request(url)
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            req.add_header('Authorization', f'Bearer {token}')
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read())
    except Exception:
        return None

    if not releases:
        return None

    latest = releases[0]
    version = latest.get('tag_name', 'v6.2.0')
    date = latest.get('published_at', '2026-05-22')[:10]
    apk_url = ''
    tar_url = ''
    for a in latest.get('assets', []):
        name = a.get('name', '')
        if name.endswith('.apk'):
            apk_url = a.get('browser_download_url', '')
        elif name.endswith('.tar.gz'):
            tar_url = a.get('browser_download_url', '')
    body = latest.get('body', '')
    changelog = md_to_html(body) if body else '<p>No changelog available.</p>'

    older_rows = []
    for r in releases[1:]:
        tag = r.get('tag_name', '')
        rd = r.get('published_at', '')[:10]
        rn = r.get('name', tag)
        older_rows.append(
            f'<tr><td>{rn}</td><td>{rd}</td>'
            f'<td><a href="https://github.com/ravindu644/Droidspaces-OSS/releases/tag/{tag}" class="dl-secondary">Download</a></td></tr>'
        )
    older_html = (
        '<div class="table-wrap"><table><thead><tr><th>Version</th><th>Date</th><th></th></tr></thead><tbody>'
        + '\n'.join(older_rows)
        + '</tbody></table></div>'
        if older_rows else ''
    )

    return {
        'version': version,
        'date': date,
        'apk_url': apk_url,
        'tar_url': tar_url,
        'changelog': changelog,
        'older_html': older_html,
    }


def fetch_kernel_patches():
    base = 'https://api.github.com/repos/ravindu644/Droidspaces-OSS/contents/Documentation/resources/kernel-patches'
    data = json.loads(urllib.request.urlopen(base).read())
    parts = []
    for item in data:
        if item['type'] == 'dir':
            name = item['name']
            sub = json.loads(urllib.request.urlopen(item['url']).read())
            parts.append(f'<div class="patch-group"><h3 class="patch-group-title">{name}</h3>')
            for s in sub:
                if s['type'] == 'dir':
                    sname = s['name']
                    sub2 = json.loads(urllib.request.urlopen(s['url']).read())
                    parts.append(f'<div class="patch-subgroup"><h4 class="patch-subgroup-title">{sname}</h4><ul class="patch-list">')
                    for s2 in sub2:
                        fname = s2['name']
                        parts.append(f'<li><a href="{s2["download_url"]}" download>{fname}</a></li>')
                    parts.append('</ul></div>')
                else:
                    parts.append(f'<ul class="patch-list"><li><a href="{s["download_url"]}" download>{s["name"]}</a></li></ul>')
            parts.append('</div>')
    return '\n'.join(parts)

def build_downloads_page(root, nav_template, footer_template):
    dl_nav = nav_template.replace('{{FEATURES_HREF}}', '/#features').replace('{{DOCS_STYLE}}', '')
    release_info = fetch_latest_release()
    patches_html = '''<div class="patch-group"><h3 class="patch-group-title">GKI</h3>
<div class="patch-subgroup"><h4 class="patch-subgroup-title">below-kernel-6.12</h4><ul class="patch-list">
<li><a href="https://raw.githubusercontent.com/ravindu644/Droidspaces-OSS/main/Documentation/resources/kernel-patches/GKI/below-kernel-6.12/001.GKI-below-6.12-fix_sysvipc_kabi_1_2_3.patch" download>001.GKI-below-6.12-fix_sysvipc_kabi_1_2_3.patch</a></li>
<li><a href="https://raw.githubusercontent.com/ravindu644/Droidspaces-OSS/main/Documentation/resources/kernel-patches/GKI/below-kernel-6.12/001.GKI-below-6.12-fix_sysvipc_kabi_3_4_5.patch" download>001.GKI-below-6.12-fix_sysvipc_kabi_3_4_5.patch</a></li>
<li><a href="https://raw.githubusercontent.com/ravindu644/Droidspaces-OSS/main/Documentation/resources/kernel-patches/GKI/below-kernel-6.12/001.GKI-below-6.12-fix_sysvipc_kabi_6_7_8.patch" download>001.GKI-below-6.12-fix_sysvipc_kabi_6_7_8.patch</a></li>
<li><a href="https://raw.githubusercontent.com/ravindu644/Droidspaces-OSS/main/Documentation/resources/kernel-patches/GKI/below-kernel-6.12/002.5.10_or_lower_use_android_abi_padding_for_posix_mqueue.patch" download>002.5.10_or_lower_use_android_abi_padding_for_posix_mqueue.patch</a></li>
</ul></div>
<div class="patch-subgroup"><h4 class="patch-subgroup-title">kernel-6.12</h4><ul class="patch-list">
<li><a href="https://raw.githubusercontent.com/ravindu644/Droidspaces-OSS/main/Documentation/resources/kernel-patches/GKI/kernel-6.12/001.GKI-6.12-or-above-fix_sysvipc_kabi.patch" download>001.GKI-6.12-or-above-fix_sysvipc_kabi.patch</a></li>
</ul></div>
</div>
<div class="patch-group"><h3 class="patch-group-title">non-GKI</h3>
<ul class="patch-list"><li><a href="https://raw.githubusercontent.com/ravindu644/Droidspaces-OSS/main/Documentation/resources/kernel-patches/non-GKI/01.fix_kernel_panic_in_xt_qtaguid.patch" download>01.fix_kernel_panic_in_xt_qtaguid.patch</a></li></ul>
<ul class="patch-list"><li><a href="https://raw.githubusercontent.com/ravindu644/Droidspaces-OSS/main/Documentation/resources/kernel-patches/non-GKI/02.fix_restore%20cgroup%20file%20prefix%20handling%20.patch" download>02.fix_restore cgroup file prefix handling .patch</a></li></ul>
</div>'''
    if release_info:
        version = release_info['version']
        date = release_info['date']
        apk_url = release_info['apk_url']
        tar_url = release_info['tar_url']
        changelog = release_info['changelog']
        older_html = release_info['older_html']
    else:
        version = 'v6.2.0'
        date = '2026-05-22'
        apk_url = 'https://github.com/ravindu644/Droidspaces-OSS/releases/download/v6.2.0/Droidspaces-universal-v6.2.0-2026-05-22.apk'
        tar_url = 'https://github.com/ravindu644/Droidspaces-OSS/releases/download/v6.2.0/droidspaces-v6.2.0-2026-05-22.tar.gz'
        changelog = md_to_html('''## What's Changed
* fix(terminal): resolve hostname before opening tabs/picker
* fix(terminal/panel): unified OSInfo stream eliminates hostname/metrics null bug
* droidspaces: bump v6.2.0
* Translated using Weblate (#144)
* fix: prevent UI remount and systemd state loss on screen rotation
* fix(service): update terminal session notification count and localize strings
* post_extract_fixes: configure systemd-networkd for eth0 and restrict systemd-resolved for NAT networking
* pipewire: use env for pw-cli in audio setup
* fix(service): update notification tap action and improve foreground service strings
* fix: allow webview dom storage for better js dialog handling
* Translated using Weblate (Chinese (Simplified))
* Translated using Weblate (Turkish)
* Translated using Weblate (Ukrainian)''')
        older_html = '<div class="table-wrap"><table><thead><tr><th>Version</th><th>Date</th><th></th></tr></thead><tbody><tr><td>v6.1.5</td><td>2026-05-15</td><td><a href="https://github.com/ravindu644/Droidspaces-OSS/releases/tag/v6.1.5" class="dl-secondary">Download</a></td></tr><tr><td>v6.1.0</td><td>2026-05-13</td><td><a href="https://github.com/ravindu644/Droidspaces-OSS/releases/tag/v6.1.0" class="dl-secondary">Download</a></td></tr><tr><td>v6.0.0</td><td>2026-04-24</td><td><a href="https://github.com/ravindu644/Droidspaces-OSS/releases/tag/v6.0.0" class="dl-secondary">Download</a></td></tr></tbody></table></div>'
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Download Droidspaces — APK for Android, tarball for Linux, kernel patches, and changelogs.">
  <title>Downloads - Droidspaces</title>
  <meta property="og:title" content="Downloads - Droidspaces">
  <meta property="og:description" content="Download Droidspaces — APK for Android, tarball for Linux, kernel patches, and changelogs.">
  <meta property="og:url" content="https://www.droidspaces.org/downloads.html">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://i.ibb.co/d4PLN7Gg/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Downloads - Droidspaces">
  <meta name="twitter:description" content="Download Droidspaces — APK for Android, tarball for Linux, kernel patches, and changelogs.">
  <meta name="twitter:image" content="https://i.ibb.co/d4PLN7Gg/og-image.png">
  <link rel="canonical" href="https://www.droidspaces.org/downloads.html">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="dns-prefetch" href="https://github.com">
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
  <link rel="stylesheet" href="style.css">
  <link rel="icon" href="/favicon.ico">
  <link rel="apple-touch-icon" href="/favicon.ico">
  <script>(function(){{const t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);}})();</script>
</head>
<body>
<!--NAV_START-->
{dl_nav}
<!--NAV_END-->
<main>
  <section class="download-hero">
    <div class="container">
      <div class="section-label">Downloads</div>
      <h1>{version}</h1>
      <p class="hero-desc">Released Date: {date}</p>
      <div class="dl-cards">
        <div class="dl-card">
          <div class="dl-card-icon"><i class="fab fa-android"></i></div>
          <h3 class="dl-card-title">Android</h3>
          <p class="dl-card-desc">APK for rooted Android devices. KernelSU, Magisk, or APatch.</p>
          <a href="{apk_url}" class="btn btn-primary dl-card-btn"><i class="fas fa-download"></i> Download APK</a>
        </div>
        <div class="dl-card">
          <div class="dl-card-icon"><i class="fab fa-linux"></i></div>
          <h3 class="dl-card-title">Linux</h3>
          <p class="dl-card-desc">Static tarball for any Linux distribution. Zero dependencies.</p>
          <a href="{tar_url}" class="btn btn-primary dl-card-btn"><i class="fas fa-download"></i> Download Tarball</a>
        </div>
      </div>
      <div style="text-align:center;margin-top:1.5rem">
        <a href="https://github.com/ravindu644/Droidspaces-OSS/releases" class="btn btn-ghost" rel="noopener noreferrer">All Releases &rarr;</a>
      </div>
    </div>
  </section>
  <div class="divider"></div>
  <section class="section">
    <div class="container">
      <div class="section-label">Kernel Patches</div>
      <h2>Download kernel patches</h2>
      <p class="section-desc">Patches for custom kernel builds. Select your kernel type and version.</p>
      {patches_html}
    </div>
  </section>
  <div class="divider"></div>
  <section class="section">
    <div class="container">
      <div class="section-label">Changelog</div>
      <h2>{version}</h2>
      <div class="changelog-wrap">
        <div class="changelog" id="changelog-body">
          {changelog}
        </div>
        <button class="changelog-toggle" id="changelog-toggle" onclick="document.getElementById('changelog-body').classList.toggle('expanded');this.textContent=this.textContent==='Show changelog'?'Hide changelog':'Show changelog'">Show changelog</button>
      </div>
    </div>
  </section>
  <div class="divider"></div>
  <section class="section">
    <div class="container">
      <div class="section-label">Older Versions</div>
      <h2>Previous releases</h2>
      {older_html}
    </div>
  </section>
</main>
<footer>
{footer_template}
</footer>
<script>
(()=>{{
  const t=document.getElementById('theme-toggle');if(!t)return;
  const s=t.querySelector('.sun-icon'),m=t.querySelector('.moon-icon'),q=window.matchMedia('(prefers-color-scheme: light)');
  function u(t){{t==='light'?(s.style.display='none',m.style.display='block'):(s.style.display='block',m.style.display='none')}}
  function g(){{const s=localStorage.getItem('theme');return s||(q.matches?'light':'dark')}}
  function a(t){{t==='system'?(document.documentElement.removeAttribute('data-theme'),u(q.matches?'light':'dark')):(document.documentElement.setAttribute('data-theme',t),u(t))}}
  a(g());q.addEventListener('change',e=>{{if(!localStorage.getItem('theme'))a(e.matches?'light':'dark')}});
  t.addEventListener('click',()=>{{const c=g(),n=c==='dark'?'light':'dark';localStorage.setItem('theme',n);a(n)}});
}})();
</script>
</body>
</html>'''
    with open(os.path.join(root, 'downloads.html'), 'w') as f:
        f.write(html)
    print("OK: downloads.html")

def generate_sitemap(root):
    base = 'https://www.droidspaces.org'
    today = '2026-05-23'
    priorities = {
        'index.html': ('/', 1.0),
        'downloads.html': ('/downloads.html', 0.9),
        '404.html': ('/404.html', 0.1),
    }
    doc_priorities = {
        'installation-android': 0.9, 'installation-linux': 0.8,
        'features': 0.7, 'gpu-acceleration': 0.7, 'kernel-configuration': 0.7,
        'usage-android-app': 0.7, 'linux-cli': 0.7, 'cool-things-you-can-do': 0.6,
        'troubleshooting': 0.6, 'community-supported-devices': 0.5,
        'nix-nixos': 0.5, 'uninstallation': 0.5,
    }
    urls = [(loc, pri) for fname, (loc, pri) in priorities.items()]
    urls += [(f'/docs/{slug}.html', pri) for slug, pri in doc_priorities.items()]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, pri in urls:
        lines.append('  <url>')
        lines.append(f'    <loc>{base}{loc}</loc>')
        lines.append(f'    <lastmod>{today}</lastmod>')
        lines.append(f'    <changefreq>monthly</changefreq>')
        lines.append(f'    <priority>{pri}</priority>')
        lines.append('  </url>')
    lines.append('</urlset>')
    with open(os.path.join(root, 'sitemap.xml'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print("OK: sitemap.xml")

if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    docs_dir = os.path.join(root, 'docs/content')
    out_dir = os.path.join(root, 'docs')

    with open(os.path.join(root, '_nav.html')) as f:
        nav_template = f.read()
    with open(os.path.join(root, '_footer.html')) as f:
        footer_template = f.read()

    pages = load_pages(docs_dir)

    for slug, title, section, order, desc, keywords, fname in pages:
        path = os.path.join(docs_dir, fname)
        if not os.path.exists(path):
            print(f"SKIP: {fname} not found")
            continue
        with open(path) as f:
            md = f.read()
        md = re.sub(r'^\s*<!--.*?-->\s*', '', md, flags=re.DOTALL)
        body = md_to_html(md)
        body = fix_img_paths(body)
        slug = fname.replace('.md', '').lower()
        page = make_page(title, body, slug, nav_template, footer_template, pages)
        out_path = os.path.join(out_dir, slug + '.html')
        with open(out_path, 'w') as f:
            f.write(page)
        print(f"OK: {slug}.html")

    # Stamp index.html
    index_path = os.path.join(root, 'index.html')
    with open(index_path) as f:
        index_html = f.read()
    index_nav = nav_template.replace('{{FEATURES_HREF}}', '#features').replace('{{DOCS_STYLE}}', '')
    index_html = re.sub(
        r'<!--NAV_START-->.*?<!--NAV_END-->',
        f'<!--NAV_START-->\n{index_nav}\n<!--NAV_END-->',
        index_html,
        flags=re.DOTALL
    )
    release_info = fetch_latest_release()

    if release_info:
        version = release_info['version']
        index_html = re.sub(
            r'(<div class="hero-badge"><span></span>)v[^<]+( · Open Source</div>)',
            lambda m: f'{m.group(1)}{version}{m.group(2)}',
            index_html,
        )
        index_html = re.sub(
            r'("softwareVersion"\s*:\s*")v?[^"\n]+("),',
            lambda m: f'{m.group(1)}{version.lstrip("v")}{m.group(2)},',
            index_html,
        )

    index_html = index_html.replace('{{FOOTER}}', footer_template)
    with open(index_path, 'w') as f:
        f.write(index_html)
    print("OK: index.html")

    # Generate downloads.html
    build_downloads_page(root, nav_template, footer_template)

    # Generate 404.html
    four04_nav = nav_template.replace('{{FEATURES_HREF}}', '/#features').replace('{{DOCS_STYLE}}', '')
    four04_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Page not found - Droidspaces">
  <title>404 - Droidspaces</title>
  <meta property="og:title" content="404 - Droidspaces">
  <meta property="og:description" content="Page not found">
  <meta property="og:url" content="https://www.droidspaces.org/404.html">
  <meta property="og:type" content="website">
  <meta property="og:image" content="https://i.ibb.co/d4PLN7Gg/og-image.png">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="404 - Droidspaces">
  <meta name="twitter:description" content="Page not found">
  <meta name="twitter:image" content="https://i.ibb.co/d4PLN7Gg/og-image.png">
  <link rel="canonical" href="https://www.droidspaces.org/404.html">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <link rel="icon" href="/favicon.ico">
  <link rel="apple-touch-icon" href="/favicon.ico">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css">
  <link rel="stylesheet" href="/style.css">
  <script>(function(){{const t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);}})();</script>
</head>
<body>
{four04_nav}
  <main style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:calc(100vh - 56px - 80px);padding:2rem;text-align:center">
    <h1 style="font-size:4rem;font-family:var(--mono);color:var(--muted);margin-bottom:0.5rem">404</h1>
    <p style="color:var(--muted);font-size:1rem;margin-bottom:2rem;max-width:400px">The page you're looking for doesn't exist.</p>
    <div style="display:flex;gap:0.75rem;flex-wrap:wrap;justify-content:center">
      <a href="/" class="btn btn-primary">Go Home</a>
      <a href="/docs/" class="btn btn-ghost">Browse Docs</a>
    </div>
  </main>
  <footer>
    <p>{footer_template}</p>
  </footer>
</body>
</html>'''
    with open(os.path.join(root, '404.html'), 'w') as f:
        f.write(four04_html)
    print("OK: 404.html")

    generate_sitemap(root)
