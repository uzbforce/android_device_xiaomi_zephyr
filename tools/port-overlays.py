#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: The LineageOS Project
# SPDX-License-Identifier: Apache-2.0
#
# Regenerate the source RROs under overlay/ from the RRO APKs in a stock
# firmware dump.
#
# Xiaomi ships this platform's device-specific resource overlays as compiled
# APKs: the "target" tier in vendor/overlay/*_Vendor.apk and the "common" tier
# in product/overlay/*ResCommon_Sys.apk.  The Lineage build owns both of those
# directories, so the blobs cannot be shipped and the overlays have to exist as
# source instead.  Every value below is read straight out of the APKs with
# aapt2, so these are the vendor's own numbers rather than a guess.
#
#   python3 tools/port-overlays.py --dump work/root
#   python3 tools/port-overlays.py --dump work/root --verify
#   python3 tools/port-overlays.py --list
#
# --verify compiles and links every generated overlay against the framework in
# the dump and diffs the resulting resource table, XML resources and manifest
# against the stock APK, which is what catches a transcription slip.
#
# aapt2 comes from the Android SDK build-tools or from a built tree
# (out/host/linux-x86/bin/aapt2).  Only the per-overlay drop list below is
# hand-maintained, and every drop names the reason it is not carried over.

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.sax.saxutils as saxutils

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

XML_HEADER = """\
<!--
     SPDX-FileCopyrightText: The LineageOS Project
     SPDX-License-Identifier: Apache-2.0
-->
"""

BP_HEADER = """\
//
// SPDX-FileCopyrightText: The LineageOS Project
// SPDX-License-Identifier: Apache-2.0
//
"""


class Overlay:
    def __init__(self, name, apk, install, module, drops=None, notes=None,
                 aaptflags=None, keep_notes=None):
        self.name = name
        self.apk = apk
        self.install = install
        self.module = module
        self.drops = drops or {}
        self.notes = notes or []
        self.aaptflags = aaptflags or []
        self.keep_notes = keep_notes or {}

    @property
    def path(self):
        return os.path.join(REPO, 'overlay', self.name)


# ---------------------------------------------------------------------------
# The port itself: one entry per stock RRO that has a target in LineageOS 23.2.
# ---------------------------------------------------------------------------
OVERLAYS = [
    # ----------------------------------------------------------------- vendor
    Overlay(
        name='FrameworksResTarget',
        apk='vendor/overlay/FrameworksResTarget_Vendor.apk',
        install='vendor',
        module='FrameworksResTarget',
        drops={
            'config_defaultPinnerServiceFiles':
                "its list names /system/framework/arm64/boot-QPerformance.oat "
                "and boot-UxPerformance.oat, which only exist in a HyperOS "
                "system image, and overriding the array replaces Lineage's "
                "default list outright - a trimmed copy would pin less, not "
                "more - so the platform default is left alone",
            'config_qualified_networks_service_package':
                'not declared by LineageOS 23.2 framework-res',
            'config_wlan_data_service_package':
                'not declared by LineageOS 23.2 framework-res',
            'config_wlan_network_service_package':
                'not declared by LineageOS 23.2 framework-res',
        },
        keep_notes={
            'config_biometric_sensors':
                'sensor id 0, type 2 (fingerprint), strength 15 '
                '(BIOMETRIC_STRENGTH_STRONG)',
            'config_useDevInputEventForAudioJack':
                'headset detection through the codec input event rather than a '
                'switch node',
            'power_profile':
                '4 x A55 (300 MHz - 1.9 GHz) + 4 x A78 (300 MHz - 2.9 GHz), '
                'battery.capacity 7700 mAh',
        },
    ),
    Overlay(
        name='WifiResTarget',
        apk='vendor/overlay/WifiResTarget_Vendor.apk',
        install='vendor',
        module='WifiResTarget',
        drops={
            'config_wifi_dual_sap_mode_enabled':
                'Qualcomm wifi fork addition: neither declared by nor listed '
                'in the overlayable policy of LineageOS 23.2 wifi resources',
        },
    ),

    # ---------------------------------------------------------------- product
    Overlay(
        name='FrameworksResCommon',
        apk='product/overlay/FrameworksResCommon_Sys.apk',
        install='product_specific',
        module='FrameworksResCommon',
        drops={
            # Qualcomm and MIUI keep their extra framework-res keys in their own
            # framework-res forks.  AOSP does not declare them, so on Lineage
            # nothing reads them.
            'config_bluetooth_hfp_inband_ringing_support':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_bluetooth_le_peripheral_mode_supported':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_dozeAfterScreenOff':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_dual_bar':
                'MIUI framework-res addition, absent from LineageOS 23.2',
            'config_wifi_background_scan_support':
                'Qualcomm framework-res addition, absent from LineageOS 23.2 '
                '(on AOSP the wifi module owns this setting)',
            'config_wifi_batched_scan_supported':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_wifi_connected_mac_randomization_supported':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_wifi_dual_band_support':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_wifi_dual_sap_mode_enabled':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_wifi_p2p_mac_randomization_supported':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_wifi_softap_acs_supported':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_wifi_softap_ieee80211ac_supported':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_emergency_apn':
                'Qualcomm framework-res addition, absent from LineageOS 23.2',
            'config_optionalPackageVerifierName':
                'MIUI: names "seemp.service", the HyperOS package verifier',
        },
    ),
    Overlay(
        name='WifiResCommon',
        apk='product/overlay/WifiResCommon_Sys.apk',
        install='product_specific',
        module='WifiResCommon',
        drops={
            # Xiaomi builds its wifi resources from a Qualcomm fork.  These five
            # exist in that fork, and in neither the config nor the overlayable
            # policy of the AOSP module, so a targetName overlay cannot set
            # them.
            'config_vendorWifi11axReadySupport':
                'Qualcomm wifi fork addition, absent from and not overlayable '
                'in LineageOS 23.2 wifi resources',
            'config_vendor_wifi_softap_owe_supported':
                'Qualcomm wifi fork addition, absent from and not overlayable '
                'in LineageOS 23.2 wifi resources',
            'config_wifiConnectedFrequencyEnhancementEnabled':
                'Qualcomm wifi fork addition, absent from and not overlayable '
                'in LineageOS 23.2 wifi resources',
            'config_wifi_batched_scan_supported':
                'Qualcomm wifi fork addition, absent from and not overlayable '
                'in LineageOS 23.2 wifi resources',
            'config_wifi_report_he_ready':
                'Qualcomm wifi fork addition, absent from and not overlayable '
                'in LineageOS 23.2 wifi resources',
        },
    ),
    Overlay(
        name='SystemUIResCommon',
        apk='product/overlay/SystemUIResCommon_Sys.apk',
        install='product_specific',
        module='SystemUIResCommon',
        keep_notes={
            'config_quickSettingsAutoAdd':
                'the two wellbeing tiles are Play Services apps and are inert '
                'without them; the entry is kept because the array replaces '
                "SystemUI's default list",
            'doze_display_state_supported':
                'legacy key that HyperOS SystemUI reads; kept as shipped',
        },
    ),
    Overlay(
        name='SettingsResCommon',
        apk='product/overlay/SettingsResCommon_Sys.apk',
        install='product_specific',
        module='SettingsResCommon',
        drops={
            'backup_calling_setting_summary':
                'HyperOS "voice over cellular internet" strings; not declared '
                'by LineageOS 23.2 Settings',
            'backup_calling_settings_title':
                'HyperOS "voice over cellular internet" strings; not declared '
                'by LineageOS 23.2 Settings',
            'keywords_backup_calling':
                'HyperOS "voice over cellular internet" strings; not declared '
                'by LineageOS 23.2 Settings',
        },
    ),
    Overlay(
        name='TelephonyResCommon',
        apk='product/overlay/TelephonyResCommon_Sys.apk',
        install='product_specific',
        module='TelephonyResCommon',
        drops={
            'config_no_sim_display_network_modes':
                'Qualcomm telephony addition, absent from LineageOS 23.2 '
                'Telephony resources',
        },
        keep_notes={
            'telephony_injection':
                'the Qualcomm injection map. It replaces the empty AOSP default '
                'in packages/services/Telephony and is what makes the QTI '
                'telephony stack load',
        },
    ),
    Overlay(
        name='TelecommResCommon',
        apk='product/overlay/TelecommResCommon_Sys.apk',
        install='product_specific',
        module='TelecommResCommon',
    ),
    Overlay(
        name='CarrierConfigResCommon',
        apk='product/overlay/CarrierConfigResCommon_Sys.apk',
        install='product_specific',
        module='CarrierConfigResCommon',
        aaptflags=['--keep-raw-values'],
        notes=[
            'aaptflags keeps the raw attribute values, exactly as the stock APK '
            'does: the framework reads this file as strings.',
        ],
    ),
    Overlay(
        name='NfcResCommon',
        apk='product/overlay/NfcResCommon_Sys.apk',
        install='product_specific',
        module='NfcResCommon',
    ),
    Overlay(
        name='NcmTetheringResCommon',
        apk='product/overlay/NcmTetheringResCommon_Sys.apk',
        install='product_specific',
        module='NcmTetheringResCommon',
        keep_notes={
            'config_tether_ncm_regexs':
                'USB-NCM tethering, which the stock kernel and init scripts '
                'support',
        },
    ),
]

# Stock overlays that are deliberately not ported, with the reason.
SKIPPED = [
    ('product/overlay/FrameworksResCommonQva_Sys.apk',
     'empty: the APK declares no resources at all'),
    ('product/overlay/CellBroadcastReceiverResCommon_Sys.apk',
     'all three of its resources (show_brazil_settings, show_cmas_settings, '
     'show_etws_settings) are Xiaomi additions to their CellBroadcastReceiver '
     'fork; LineageOS 23.2 declares none of them'),
    ('product/overlay/MccMncOverlay.apk',
     'every resource in it (status_bar_hide_volte, show_vowifi_qs, ...) is a '
     'HyperOS SystemUI resource; AOSP SystemUI declares none of them'),
    ('product/overlay/SettingsRroDevice*Overlay.apk',
     'com.miui.settings.rro.* packages, targeting MIUI Settings'),
    ('product/overlay/Gms*Overlay.apk, Google*Overlay.apk, Devices*.apk',
     'Google-built overlays for the GMS product; nothing here for them to '
     'override'),
    ('product/overlay/Miui*Overlay.apk, Mi*Overlay.apk',
     'target com.miui.* / com.xiaomi.* packages that do not exist here'),
    ('product/overlay/Aosp*Overlay.apk',
     'the AOSP resource defaults Google ships on the product image; the '
     'Lineage sources already carry those values'),
    ('product/overlay/*__auto_generated_characteristics_rro.apk',
     'generated by the build from the device characteristics'),
]


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def aapt2_dump(aapt2, apk, what):
    return run([aapt2, 'dump', *what, apk]).stdout


# ---------------------------------------------------------------- parsing


class Value:
    """One resource value: a scalar, an array, or an xml file reference."""

    def __init__(self, kind, text=None, items=None, file=None):
        self.kind = kind
        self.text = text
        self.items = items
        self.file = file

    def key(self):
        return (self.kind, self.text, tuple(self.items) if self.items else None,
                self.file)


def parse_manifest(aapt2, apk):
    out = aapt2_dump(aapt2, apk, ['xmltree', '--file', 'AndroidManifest.xml'])
    info = {'package': None, 'targetPackage': None, 'targetName': None,
            'priority': 0, 'isStatic': False}
    m = re.search(r'package="([^"]+)"', out)
    if m:
        info['package'] = m.group(1)
    for key in ('targetPackage', 'targetName'):
        m = re.search(key + r'\(0x[0-9a-f]+\)="([^"]*)"', out)
        if m:
            info[key] = m.group(1)
    m = re.search(r'priority\(0x[0-9a-f]+\)=(\d+)', out)
    if m:
        info['priority'] = int(m.group(1))
    info['isStatic'] = bool(re.search(r'isStatic\(0x[0-9a-f]+\)=true', out))
    return info


TYPE_TAGS = {
    'bool': 'bool',
    'integer': 'integer',
    'string': 'string',
    'dimen': 'dimen',
    'color': 'color',
    'fraction': 'fraction',
}


def split_array(body):
    """Split the body of a dumped array into its items."""
    items, cur, in_str, esc = [], '', False, False
    for ch in body:
        if esc:
            cur += ch
            esc = False
        elif ch == '\\':
            cur += ch
            esc = True
        elif ch == '"':
            in_str = not in_str
            cur += ch
        elif ch == ',' and not in_str:
            items.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        items.append(cur.strip())
    return items


def parse_resources(aapt2, apk):
    """Return [(type, name, {qualifier: Value})] in table order."""
    lines = aapt2_dump(aapt2, apk, ['resources']).splitlines()
    resources, cur_type, cur_name = [], None, None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^  type (\w+) id=\d+ entryCount=', line)
        if m:
            cur_type = m.group(1)
            i += 1
            continue
        m = re.match(r'^    resource 0x[0-9a-f]+ \w+/(\w+)$', line)
        if m:
            cur_name = m.group(1)
            resources.append((cur_type, cur_name, {}))
            i += 1
            continue
        m = re.match(r'^      \(([^)]*)\) (.*)$', line)
        if m and cur_name:
            qual, rest = m.group(1), m.group(2)
            if rest.startswith('(array)'):
                j = i + 1
                while j < len(lines) and '[' not in lines[j]:
                    j += 1
                body = ''
                while j < len(lines):
                    body += lines[j].strip()
                    if body.endswith(']'):
                        break
                    j += 1
                inner = body[body.index('[') + 1:body.rindex(']')]
                raw = split_array(inner)
                if raw and raw[0].startswith('"'):
                    val = Value('string-array',
                                items=[x[1:-1].replace('\\"', '"') for x in raw])
                else:
                    val = Value('integer-array', items=raw)
                i = j + 1
            elif rest.startswith('(file)'):
                val = Value('xml-file', file=rest.split()[1])
                i += 1
            elif rest in ('true', 'false'):
                val = Value('bool', text=rest)
                i += 1
            elif re.match(r'^-?\d+$', rest):
                val = Value(cur_type if cur_type in TYPE_TAGS else 'integer',
                            text=rest)
                i += 1
            elif rest.startswith('"'):
                val = Value('string', text=rest[1:-1])
                i += 1
            elif re.match(r'^-?[\d.]+(dp|dip|sp|pt|in|mm|px|%)?$', rest):
                val = Value('dimen', text=rest)
                i += 1
            else:
                val = Value('unknown', text=rest)
                i += 1
            resources[-1][2][qual] = val
            continue
        i += 1
    return resources


class XmlNode:
    def __init__(self, tag):
        self.tag = tag
        self.attrs = []
        self.text = None
        self.children = []


def parse_xmltree(aapt2, apk, path):
    out = aapt2_dump(aapt2, apk, ['xmltree', '--file', path])
    root, stack, pending = None, [], None
    for line in out.splitlines():
        m = re.match(r'^(\s*)E: (\S+)', line)
        if m:
            indent = len(m.group(1))
            node = XmlNode(m.group(2))
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                stack[-1][1].children.append(node)
            else:
                root = node
            stack.append((indent, node))
            pending = node
            continue
        m = re.match(r'^\s*A: (\S+?)=(\S*?)(?:\s+\(Raw: "(.*)"\))?$', line)
        if m and pending is not None:
            name = re.sub(r'\(0x[0-9a-f]+\)$', '', m.group(1))
            name = name.replace(
                'http://schemas.android.com/apk/res/android:', 'android:')
            pending.attrs.append((name, m.group(3) if m.group(3) is not None
                                  else m.group(2)))
            continue
        m = re.match(r"^\s*T: '(.*)'$", line)
        if m and pending is not None:
            pending.text = (pending.text or '') + m.group(1)
    return root


# ---------------------------------------------------------------- emitting


def xml_escape(text):
    return saxutils.escape(text, {'"': '&quot;', "'": '&apos;'})


def android_escape(text):
    """Escape a string so that it round-trips back through aapt2 unchanged."""
    out = (text.replace('\\', '\\\\').replace('"', '\\"')
           .replace("'", "\\'").replace('\n', '\\n').replace('\t', '\\t'))
    if out[:1] in ('@', '?'):
        out = '\\' + out
    return out


LOCALE_RE = re.compile(r'(?:^|-)((?:[a-z]{2,3})(?:-r[A-Z]{2})?|b\+[A-Za-z0-9+]+)$')


def split_locale(qual):
    """Split a qualifier into (base, locale) with a trailing locale removed."""
    m = LOCALE_RE.search(qual)
    if not m:
        return qual, ''
    base = qual[:m.start()].strip('-')
    return base, m.group(1)


def collapse_locales(by_qual):
    """Drop locale-qualified variants that repeat the value of their base."""
    groups = {}
    for qual, val in by_qual.items():
        base, locale = split_locale(qual)
        groups.setdefault(base, []).append((qual, locale, val))
    out, collapsed = {}, []
    for base, entries in groups.items():
        if len({e[2].key() for e in entries}) == 1:
            out[base] = entries[0][2]
            collapsed += [qual for qual, locale, _ in entries if locale]
        else:
            for qual, _, val in entries:
                out[qual] = val
    return out, collapsed


VALUE_GROUPS = {'bool': 'booleans', 'integer': 'integers', 'string': 'strings',
                'dimen': 'dimensions'}


def render_value(name, val, comment=None):
    lines = []
    for line in wrap(comment, '') if comment else []:
        lines.append('    <!-- %s -->' % line)
    if val.kind == 'string-array':
        lines.append('    <string-array name="%s" translatable="false">' % name)
        for item in val.items:
            lines.append('        <item>%s</item>'
                         % xml_escape(android_escape(item)))
        lines.append('    </string-array>')
    elif val.kind == 'integer-array':
        lines.append('    <integer-array name="%s" translatable="false">' % name)
        for item in val.items:
            lines.append('        <item>%s</item>' % item)
        lines.append('    </integer-array>')
    elif val.kind == 'string':
        lines.append('    <string name="%s" translatable="false">%s</string>'
                     % (name, xml_escape(android_escape(val.text))))
    elif val.kind == 'dimen':
        lines.append('    <dimen name="%s">%s</dimen>'
                     % (name, format_dimen(val.text)))
    else:
        tag = TYPE_TAGS.get(val.kind, val.kind)
        lines.append('    <%s name="%s">%s</%s>' % (tag, name, val.text, tag))
    return lines


def format_dimen(text):
    """20.000000dp reads better as 20dp; the compiled value is the same."""
    m = re.match(r'^(-?[\d.]+)(dp|dip|sp|pt|in|mm|px|%)?$', text)
    if not m:
        return text
    number = m.group(1)
    if '.' in number:
        number = number.rstrip('0').rstrip('.')
    return number + (m.group(2) or '')


def render_xml(node, indent=0):
    pad = ' ' * indent
    attrs = ''.join(' %s="%s"' % (k, xml_escape(v)) for k, v in node.attrs)
    if not node.children and node.text is None:
        return ['%s<%s%s />' % (pad, node.tag, attrs)]
    if not node.children:
        return ['%s<%s%s>%s</%s>'
                % (pad, node.tag, attrs, xml_escape(node.text), node.tag)]
    lines = ['%s<%s%s>' % (pad, node.tag, attrs)]
    for child in node.children:
        lines += render_xml(child, indent + 4)
    lines.append('%s</%s>' % (pad, node.tag))
    return lines


def wrap(text, indent='', width=78):
    """Wrap a comment paragraph at the given indent."""
    lines, cur = [], indent
    for word in text.split():
        if cur.strip() and len(cur) + len(word) + 1 > width:
            lines.append(cur.rstrip())
            cur = indent
        cur += word + ' '
    if cur.strip():
        lines.append(cur.rstrip())
    return lines


def bullet(name, text, indent='     ', width=78):
    """One bullet, on a single line when it fits, otherwise wrapped under it."""
    line = '%s* %s: %s' % (indent, name, text)
    if len(line) <= width:
        return [line]
    return ['%s* %s:' % (indent, name)] + wrap(text, indent + '  ')


def file_header(apk, firmware, notes=(), drops=None):
    out = [XML_HEADER, '<!--']
    out += wrap('Regenerated from %s of %s by tools/port-overlays.py.'
                % (apk, firmware), '     ')
    out += wrap('The values are the ones the stock overlay itself carries.',
                '     ')
    for note in notes:
        out.append('')
        out += wrap(note, '     ')
    if drops:
        out += ['', '     Not carried over:']
        for name, why in drops.items():
            out += bullet(name, why)
    out.append('-->')
    return out


def emit_overlay(ov, dump_root, firmware):
    apk = os.path.join(dump_root, ov.apk)
    if not os.path.exists(apk):
        raise SystemExit('%s: missing from the dump' % ov.apk)

    manifest = parse_manifest(ARGS.aapt2, apk)
    resources = [(t, n, q) for t, n, q in parse_resources(ARGS.aapt2, apk)
                 if n not in ov.drops]

    for t, n, q in resources:
        for val in q.values():
            if val.kind == 'unknown':
                raise SystemExit('%s/%s: unsupported value %r, the parser needs '
                                 'to learn about it' % (ov.name, n, val.text))

    outdir = ov.path
    if os.path.isdir(outdir):
        shutil.rmtree(outdir)
    os.makedirs(os.path.join(outdir, 'res'))

    by_dir, xml_files = {}, []
    for t, n, q in resources:
        collapsed, notes = collapse_locales(q)
        if notes:
            print('  %s: collapsed locale-only variants of %s (%s)'
                  % (ov.name, n, ', '.join(notes)))
        for qual, val in collapsed.items():
            if val.kind == 'xml-file':
                xml_files.append((n, val.file))
            else:
                by_dir.setdefault(qual, []).append((n, val))

    files = []
    primary = True
    for qual in sorted(by_dir, key=lambda q: (q != '', q)):
        entries = by_dir[qual]
        kinds = {v.kind for _, v in entries}
        if kinds <= {'string'}:
            fname = 'strings.xml'
        elif kinds <= {'dimen'}:
            fname = 'dimens.xml'
        else:
            fname = 'config.xml'
        subdir = 'values' if qual == '' else 'values-' + qual
        body = ['<?xml version="1.0" encoding="utf-8"?>']
        body += file_header(ov.apk, firmware, ov.notes if primary else [],
                            ov.drops if primary else None)
        primary = False
        body.append('<resources>')
        last_group = None
        for name, val in entries:
            group = VALUE_GROUPS.get(val.kind, 'arrays')
            if group != last_group and last_group is not None:
                body.append('')
            last_group = group
            body += render_value(name, val, ov.keep_notes.get(name))
        body += ['</resources>', '']
        files.append((os.path.join('res', subdir, fname), '\n'.join(body)))

    for name, path in xml_files:
        src = parse_xmltree(ARGS.aapt2, apk, path)
        if src is None:
            raise SystemExit('%s: could not parse %s' % (ov.name, path))
        body = ['<?xml version="1.0" encoding="utf-8"?>']
        body += file_header(ov.apk, firmware,
                            ([ov.keep_notes[name]] if name in ov.keep_notes
                             else []) + (ov.notes if primary else []),
                            ov.drops if primary else None)
        primary = False
        body += render_xml(src)
        body.append('')
        files.append((os.path.join('res', 'xml', os.path.basename(path)),
                      '\n'.join(body)))

    for path, content in files:
        full = os.path.join(outdir, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'w', encoding='utf-8') as fh:
            fh.write(content)

    bp = [BP_HEADER, 'runtime_resource_overlay {', '    name: "%s",' % ov.module]
    if ov.aaptflags:
        bp.append('    aaptflags: [%s],'
                  % ', '.join('"%s"' % f for f in ov.aaptflags))
    bp += ['    %s: true,' % ov.install, '}', '']
    with open(os.path.join(outdir, 'Android.bp'), 'w') as fh:
        fh.write('\n'.join(bp))

    mf = ['<?xml version="1.0" encoding="utf-8"?>', XML_HEADER, '<!--',
          '     Same package name, target package and priority as the stock',
          '     %s this replaces.' % os.path.basename(ov.apk), '-->',
          '<manifest xmlns:android="http://schemas.android.com/apk/res/android"',
          '    package="%s">' % manifest['package'],
          '    <overlay android:targetPackage="%s"' % manifest['targetPackage']]
    if manifest['targetName']:
        mf.append('             android:targetName="%s"' % manifest['targetName'])
    mf += ['             android:isStatic="true"',
           '             android:priority="%d"/>' % manifest['priority'],
           '</manifest>', '']
    with open(os.path.join(outdir, 'AndroidManifest.xml'), 'w') as fh:
        fh.write('\n'.join(mf))

    print('  %-22s %-42s %2d resources, %d dropped'
          % (ov.name, ov.apk, len(resources), len(ov.drops)))
    return manifest


# --------------------------------------------------------------- verifying


def normalize(resources):
    out = {}
    for t, n, q in resources:
        collapsed, _ = collapse_locales(q)
        out[n] = (t, {k: v.key() for k, v in collapsed.items()})
    return out


def verify(ov, dump_root):
    aapt2 = ARGS.aapt2
    stock = os.path.join(dump_root, ov.apk)
    tmp = tempfile.mkdtemp(prefix='port-overlays-')
    try:
        zip_path = os.path.join(tmp, ov.name + '.zip')
        run([aapt2, 'compile', '--dir', os.path.join(ov.path, 'res'),
             '-o', zip_path])
        built = os.path.join(tmp, ov.name + '.apk')
        run([aapt2, 'link', '-o', built,
             '--manifest', os.path.join(ov.path, 'AndroidManifest.xml'),
             '-I', os.path.join(dump_root, 'system/framework/framework-res.apk'),
             *ov.aaptflags, zip_path])

        problems = []
        stock_m = parse_manifest(aapt2, stock)
        built_m = parse_manifest(aapt2, built)
        for key in ('package', 'targetPackage', 'targetName', 'priority',
                    'isStatic'):
            if stock_m[key] != built_m[key]:
                problems.append('manifest %s: stock %r != built %r'
                                % (key, stock_m[key], built_m[key]))

        stock_r = normalize(parse_resources(aapt2, stock))
        built_r = normalize(parse_resources(aapt2, built))
        for name in ov.drops:
            if name not in stock_r:
                problems.append('drop list names %s, which the stock APK does '
                                'not have' % name)
            stock_r.pop(name, None)
        for name in sorted(set(stock_r) | set(built_r)):
            if name not in stock_r:
                problems.append('%s is in the built overlay but not in the '
                                'stock APK' % name)
                continue
            if name not in built_r:
                problems.append('%s is missing from the built overlay' % name)
                continue
            st, sv = stock_r[name]
            bt, bv = built_r[name]
            if st != bt:
                problems.append('%s: type %s != %s' % (name, st, bt))
            for qual in sorted(set(sv) | set(bv)):
                if sv.get(qual) != bv.get(qual):
                    problems.append('%s(%s): %r != %r'
                                    % (name, qual or 'default', sv.get(qual),
                                       bv.get(qual)))

        for name, (_, values) in sorted(stock_r.items()):
            for qual, key in values.items():
                if key[0] != 'xml-file':
                    continue
                path = key[3]
                norm = lambda ls: [re.sub(r'\s*\(line=\d+\)', '', l).strip()
                                   for l in ls]
                s = norm(aapt2_dump(aapt2, stock, ['xmltree', '--file', path]).splitlines())
                b = norm(aapt2_dump(aapt2, built, ['xmltree', '--file', path]).splitlines())
                if s != b:
                    problems.append('xml resource %s differs from the stock '
                                    'copy of %s' % (name, path))
                    for sl, bl in zip(s + [''] * 20, b + [''] * 20):
                        if sl != bl:
                            problems.append('    stock: %s\n    built: %s' % (sl, bl))

        if problems:
            print('  %s: FAILED' % ov.name)
            for p in problems:
                print('      %s' % p)
            return False
        print('  %-22s verified against the stock APK' % ov.name)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    global ARGS
    ap = argparse.ArgumentParser(
        description='Regenerate the overlay sources from the stock RRO APKs.')
    ap.add_argument('--dump', default=os.path.join(REPO, 'work/root'),
                    help='extracted firmware tree (the directory holding '
                         'vendor/, product/ and system/)')
    ap.add_argument('--aapt2', default=os.environ.get('AAPT2', 'aapt2'))
    ap.add_argument('--firmware', default='the stock firmware dump',
                    help='firmware name to record in the generated headers')
    ap.add_argument('--verify', action='store_true',
                    help='compile and diff every overlay against the stock APK')
    ap.add_argument('--list', action='store_true',
                    help='list the stock overlays and what happens to each')
    ap.add_argument('--only', action='append', default=[],
                    help='restrict the run to one overlay (repeatable)')
    ARGS = ap.parse_args()

    if ARGS.list:
        print('Ported:')
        for ov in OVERLAYS:
            print('  %-46s -> overlay/%s' % (ov.apk, ov.name))
        print('\nNot ported:')
        for path, why in SKIPPED:
            print('  %-46s %s' % (path, why))
        return 0

    selected = [ov for ov in OVERLAYS if not ARGS.only or ov.name in ARGS.only]
    if not selected:
        raise SystemExit('nothing matches %r' % ARGS.only)
    if not os.path.isdir(os.path.join(ARGS.dump, 'product')):
        raise SystemExit('%s does not look like an extracted dump' % ARGS.dump)

    failures = 0
    for ov in selected:
        emit_overlay(ov, ARGS.dump, ARGS.firmware)
        if ARGS.verify and not verify(ov, ARGS.dump):
            failures += 1
    if failures:
        print('\n%d overlay(s) failed verification' % failures)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
