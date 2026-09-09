import json
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

PRIMARY_GUIDE = ROOT / "guide-iptv-org.xml"
FALLBACK_MAPPING = ROOT / "epg_pw_fallback.json"
FINAL_GUIDE = ROOT / "guide.xml"

USER_AGENT = "Mozilla/5.0 (EPG fallback updater)"
REQUEST_TIMEOUT = 30


def download_xml(url):
    """Download an XML document and return its root element."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        data = response.read()

    return ET.fromstring(data)


def has_programmes(root, xmltv_id):
    """Return True if the primary guide already has programmes for this ID."""
    for programme in root.findall("programme"):
        if programme.get("channel") == xmltv_id:
            return True

    return False


def get_programmes(root):
    """Return all programme elements from an EPG.PW document."""
    return root.findall("programme")


def main():
    if not PRIMARY_GUIDE.exists():
        print(f"ERROR: {PRIMARY_GUIDE} does not exist.")
        sys.exit(1)

    if not FALLBACK_MAPPING.exists():
        print(f"ERROR: {FALLBACK_MAPPING} does not exist.")
        sys.exit(1)

    print("Loading primary iptv-org guide...")
    primary_tree = ET.parse(PRIMARY_GUIDE)
    primary_root = primary_tree.getroot()

    print("Loading EPG.PW fallback mapping...")
    with FALLBACK_MAPPING.open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    channels = mapping.get("channels", [])

    if not channels:
        print("WARNING: No fallback channels found.")
        primary_tree.write(
            FINAL_GUIDE,
            encoding="UTF-8",
            xml_declaration=True
        )
        return

    base_url = mapping["base_url"]

    added = 0
    skipped = 0
    failed = 0

    for item in channels:
        iptv_org_id = item["iptv_org_id"]
        epg_pw_id = item["epg_pw_channel_id"]
        epg_pw_name = item.get("epg_pw_name", epg_pw_id)

        print()
        print(f"Checking: {iptv_org_id}")
        print(f"  EPG.PW: {epg_pw_name} ({epg_pw_id})")

        # Never overwrite an existing iptv-org schedule.
        if has_programmes(primary_root, iptv_org_id):
            print("  iptv-org already has programmes -> keeping iptv-org")
            skipped += 1
            continue

        url = base_url.format(channel_id=epg_pw_id)

        try:
            fallback_root = download_xml(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  ERROR downloading EPG.PW: {exc}")
            failed += 1
            continue
        except ET.ParseError as exc:
            print(f"  ERROR parsing EPG.PW XML: {exc}")
            failed += 1
            continue

        programmes = get_programmes(fallback_root)

        if not programmes:
            print("  No programmes returned by EPG.PW")
            failed += 1
            continue

        count = 0

        for programme in programmes:
            # Make a copy instead of modifying the downloaded XML tree.
            new_programme = ET.fromstring(
                ET.tostring(programme, encoding="unicode")
            )

            # This is the critical mapping:
            #
            # EPG.PW's channel ID -> your iptv-org XMLTV ID
            #
            # That allows TiviMate to match the schedule to your M3U.
            new_programme.set("channel", iptv_org_id)

            primary_root.append(new_programme)
            count += 1

        added += count

        print(f"  Added {count} programmes")

        # Be polite to EPG.PW.
        time.sleep(1)

    # Write the final merged XMLTV guide.
    ET.indent(primary_root, space="  ")

    primary_tree.write(
        FINAL_GUIDE,
        encoding="UTF-8",
        xml_declaration=True
    )

    print()
    print("=" * 60)
    print("EPG MERGE COMPLETE")
    print("=" * 60)
    print(f"Fallback mappings checked: {len(channels)}")
    print(f"Fallback programmes added: {added}")
    print(f"Skipped because iptv-org had data: {skipped}")
    print(f"Failed / no data: {failed}")
    print(f"Final guide: {FINAL_GUIDE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
