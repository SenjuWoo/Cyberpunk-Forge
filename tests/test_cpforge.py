"""Offline test suite. Builds a fake game tree; needs no real game, network or Windows."""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cpforge import __version__  # noqa: E402
from cpforge import archive, check, cli, conflicts, deploy, index, knowledge, logs, nexus, package, project, redscript, tweakdb, tweaksrc, util  # noqa: E402,E501

SCRIPT = """
importonly abstract class IScriptable
{
}

class GameObject extends IScriptable
{
	public import final function RegisterInputListener( listener : IScriptable, optional name : CName );
	protected event OnGameAttached()
	{
	}
}

class PlayerPuppet extends GameObject
{
	var m_health : Float;
	protected event OnGameAttached()
	{
		var x : Int32;
	}

	protected event OnAction( action : ListenerAction, consumer : ListenerActionConsumer )
	{
	}

	public const function GetHealth() : Float
	{
		return m_health;
	}
}

importonly class Clothing_Record extends TweakDBRecord
{
}

import class ScriptableSystem extends IScriptable
{
	private export virtual function OnAttach();
}

enum EFoo
{
	A = 0,
	B = 1,
}

function GlobalHelper( a : Int32 ) : Bool
{
	return true;
}
"""

TWEAK = """package Items
using RTDB

GenericFaceClothing : Clothing
{
	quality = "Quality.Common";
}

Preset_Lexington_Default : WeaponItem
{
	displayName = "LocKey#1";
}
"""


def write_tweakdb_bin(path: Path, names_types: dict[str, str]) -> None:
    recs = b"".join(struct.pack("<QI", util.tweakdb_id(n), util.record_type_key(t)) for n, t in names_types.items())
    body = struct.pack("<i", len(names_types)) + recs
    header_len = 4 + 28
    header = struct.pack("<IiiIiiii", tweakdb.BIN_MAGIC, 8, 4, 0, header_len, header_len, header_len + len(body), header_len + len(body))
    path.write_bytes(header + body)


def red_string(s: str) -> bytes:
    raw = s.encode("latin-1")
    n = len(raw)
    if n < 0x40:
        return bytes([0x80 | n]) + raw
    first = 0x80 | 0x40 | (n & 0x3F)
    rest = n >> 6
    out = bytearray([first])
    while True:
        b = rest & 0x7F
        rest >>= 7
        out.append(b | (0x80 if rest else 0))
        if not rest:
            break
    return bytes(out) + raw


def make_game(root: Path) -> Path:
    (root / "bin/x64").mkdir(parents=True)
    (root / "bin/x64/Cyberpunk2077.exe").write_bytes(b"MZ")
    (root / "r6/cache").mkdir(parents=True)
    write_tweakdb_bin(root / "r6/cache/tweakdb.bin", {
        "Items.GenericFaceClothing": "Clothing", "Items.Preset_Lexington_Default": "WeaponItem",
        "Character.Judy": "Character", "Quality.Common": "Quality"})
    sdir = root / "tools/redmod/scripts/core"
    sdir.mkdir(parents=True)
    (sdir / "player.script").write_text(SCRIPT, encoding="utf-8")
    tdir = root / "tools/redmod/tweaks/base"
    tdir.mkdir(parents=True)
    (tdir / "items.tweak").write_text(TWEAK, encoding="utf-8")
    meta = {"classes": [{"name": "ListenerAction", "parent": "IScriptable", "properties": [],
                         "functions": [{"name": "GetName"}], "static_functions": []},
                        {"name": "WeaponItem_Record", "parent": "TweakDBRecord", "properties": [], "functions": [],
                         "static_functions": []},
                        {"name": "Character_Record", "parent": "TweakDBRecord", "properties": [], "functions": [],
                         "static_functions": []},
                        {"name": "Quality_Record", "parent": "TweakDBRecord", "properties": [], "functions": [],
                         "static_functions": []}],
            "enums": [{"name": "gameinputActionType", "options": {"BUTTON_PRESSED": 0}}],
            "global_functions": [{"name": "LogChannel"}], "bitfields": [], "aliases": {}, "simple_types": []}
    (root / "tools/redmod/metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    for d in ("r6/scripts", "r6/tweaks", "archive/pc/mod", "red4ext/plugins", "r6/logs",
              "bin/x64/plugins/cyber_engine_tweaks/mods"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "red4ext/RED4ext.dll").write_bytes(b"MZ")
    (root / "engine/tools").mkdir(parents=True)
    (root / "engine/tools/scc.exe").write_bytes(b"MZ")
    return root


def run_cli(*argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(list(argv))
    return code, json.loads(buf.getvalue())


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cpforge-test-"))
        self.home = self.tmp / "home"
        os.environ["CPFORGE_HOME"] = str(self.home)
        self.game = make_game(self.tmp / "Cyberpunk 2077 (test) !")
        os.environ["CP2077_ROOT"] = str(self.game)
        index._CACHE.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class HashTests(unittest.TestCase):
    def test_fnv1a64_vectors(self):
        self.assertEqual(util.fnv1a64(""), 0xCBF29CE484222325)
        self.assertEqual(util.fnv1a64("a"), 0xAF63DC4C8601EC8C)

    def test_archive_path_normalisation(self):
        self.assertEqual(util.archive_path("Base/Characters//X.ent"), "base\\characters\\x.ent")
        self.assertEqual(util.resource_hash("a/B"), util.fnv1a64("a\\b"))

    def test_tweakdb_id(self):
        n = "Character.Judy"
        self.assertEqual(util.tweakdb_id(n), zlib.crc32(n.encode()) | (len(n) << 32))

    def test_murmur3_and_record_keys(self):
        self.assertEqual(util.murmur3_32(b"", 0), 0)
        self.assertEqual(util.murmur3_32(b"hello", 0), 0x248BFA47)
        # Values read from a real 2.5 tweakdb.bin.
        self.assertEqual(util.record_type_key("Character"), 0x6CD8E482)
        self.assertEqual(util.record_type_key("gamedataVehicle_Record"), 0xA85E23C0)
        self.assertEqual(util.record_type_key("Clothing_Record"), 0xB926EC11)


class ArchiveTests(Base):
    def test_roundtrip_and_find(self):
        a = self.game / "archive/pc/mod/test.archive"
        archive.write_test_archive(a, {"mymod\\factories\\x.csv": b"csv", "mymod\\loc\\en.json": b"{}"})
        arc = archive.read_archive(a)
        self.assertEqual(arc.file_count, 2)
        self.assertTrue(arc.contains("MyMod/factories/x.csv"))
        self.assertFalse(arc.contains("other.csv"))
        self.assertEqual(archive.find_resource("mymod\\loc\\en.json", [a]), [str(a)])

    def test_rejects_non_archive(self):
        p = self.tmp / "bad.archive"
        p.write_bytes(b"x" * 64)
        with self.assertRaises(util.ForgeError):
            archive.read_archive(p)


class TweakDBTests(Base):
    def test_bin_and_exists(self):
        tdb = tweakdb.TweakDB(self.game)
        self.assertTrue(tdb.exists("Character.Judy"))
        self.assertFalse(tdb.exists("Character.Nobody"))
        self.assertEqual(tdb.type_key("Character.Judy"), util.record_type_key("Character"))

    def test_str_names(self):
        names = ["Items.A", "Items." + "B" * 80]
        data = struct.pack("<IIIII", tweakdb.STR_MAGIC, 1, len(names), 1, 0) + b"".join(red_string(n) for n in names) + red_string("Items.A.flat")
        p = self.tmp / "t.str"
        p.write_bytes(data)
        out = tweakdb.read_str(p)
        self.assertEqual(out["records"], names)
        self.assertEqual(out["flats"], ["Items.A.flat"])

    def test_yaml_tags_and_split(self):
        p = self.tmp / "t.yaml"
        p.write_text("Items.New:\n  $base: Items.GenericFaceClothing\n  tags: !append [A]\nItems.X.price: 5\n", encoding="utf-8")
        recs = tweakdb.yaml_records(p)
        self.assertIn("Items.New", recs["records"])
        self.assertEqual(recs["records"]["Items.New"]["base"], "Items.GenericFaceClothing")
        self.assertIn("Items.X.price", recs["flats"])


RED_TWEAK_OK = """package Items
using RTDB, BaseStats

// constructs seen in vanilla 2.5 sources and installed mods
[ notQueryable ]
MyJacket : GenericFaceClothing
{
	CName[] tags += [ "Quest", "Jacket", ];
	fk< StatModifier >[] statModifiers =
	[
		{
			statType = "BaseStats.Armor";
			value = 10.0f;
		} : Quality.Common,
		"Quality.Common"
	];
	Vector3 offset = ( 0.0f, -9.f, 0.5f );
	vehicleUIData = { productionYear = "2075"; info = "LocKey#45371"; };
	entityTemplatePath = "base\\characters\\x.ent";
}

BaseLess
{
	string value = "Friendly";
}

Vehicle.dotted_name : Character
{enumName = "x";}

float topLevelFlat = 10.f;
string[] topLevelList = [ "A", "B" ];
"""


class TweakSourceTests(Base):
    def test_parses_real_constructs(self):
        p = tweaksrc.parse(RED_TWEAK_OK)
        self.assertIsNone(p["error"], p["error"])
        self.assertEqual(p["package"], "Items")
        self.assertEqual(p["using"], ["RTDB", "BaseStats"])
        names = tweaksrc.full_names(p)
        self.assertIn("Items.MyJacket", names)
        self.assertIn("Items.BaseLess", names)
        self.assertIn("Vehicle.dotted_name", names)
        self.assertEqual(names["Items.MyJacket"]["base"], "GenericFaceClothing")
        self.assertIn("topLevelFlat", p["flats"])

    def test_syntax_errors_are_located(self):
        cases = {
            "R : Clothing\n{\n\ta = 1\n\tb = 2;\n}\n": ("TWEAK-SRC-SEMICOLON", 3),
            "R : Clothing\n{\n\ta = [ \"x\" \"y\" ];\n}\n": ("TWEAK-SRC-COMMA", 3),
            "R : Clothing\n{\n\ta = \"open;\n}\n": ("TWEAK-SRC-STRING", 3),
            "R : Clothing\n{\n\ta = 1;\n": ("TWEAK-SRC-UNCLOSED", 3),
            "R : Clothing\n{\n\t\"x\";\n}\n": ("TWEAK-SRC-STATEMENT", 3),
            "R : Clothing\n{\n}\nR : Clothing\n{\n}\n": ("TWEAK-SRC-DUP", 4),
        }
        for text, (code, line) in cases.items():
            err = tweaksrc.parse(text)["error"]
            self.assertIsNotNone(err, text)
            self.assertEqual((err["code"], err["line"]), (code, line), text)

    def test_index_keeps_baseless_and_dotted_records(self):
        (self.game / "tools/redmod/tweaks/base/extra.tweak").write_text(
            "package Extra\n\nbaseState\n{\n\tfloat x = 1.f;\n}\n\nOther.full_name : Character\n{\n}\n", encoding="utf-8")
        idx = index.build(self.game)
        self.assertIn("Extra.baseState", idx["tweak_records"])
        self.assertIn("Other.full_name", idx["tweak_records"])

    def test_check_project_reports_tweak_source(self):
        out = self.tmp / "proj"
        project.new_project("Tweak Mod", ["tweakxl"], out, "T", "d")
        index.build(self.game)
        d = out / "game/r6/tweaks/TweakMod"
        d.mkdir(parents=True, exist_ok=True)
        (d / "good.tweak").write_text(RED_TWEAK_OK.replace("BaseStats.Armor", "Quality.Common"), encoding="utf-8")
        (d / "bases.tweak").write_text("package Items\n\nA : NoSuchBase\n{\n\tquality = \"Items.Nope\";\n}\n"
                                       "B : Clothing\n{\n}\nC : gamedataCharacter_Record\n{\n}\n", encoding="utf-8")
        r = check.check_project(out)
        self.assertEqual(r["errors"], [], r["errors"])
        warns = [(w["code"], w["file"].rsplit("/", 1)[-1]) for w in r["warnings"] if w["code"].startswith("TWEAK-SRC")]
        self.assertIn(("TWEAK-SRC-BASE", "bases.tweak"), warns)
        self.assertIn(("TWEAK-SRC-REF", "bases.tweak"), warns)
        self.assertEqual([w for w in warns if w[1] == "good.tweak"], [])
        self.assertEqual(len([w for w in warns if w[0] == "TWEAK-SRC-BASE"]), 1)  # Clothing and gamedata types resolve
        (d / "broken.tweak").write_text("X : Clothing\n{\n\ta = 1\n}\n", encoding="utf-8")
        r = check.check_project(out)
        self.assertEqual([(e["code"], e["line"]) for e in r["errors"]], [("TWEAK-SRC-SEMICOLON", 3)])
        self.assertIn("tweak source syntax", r["checked"])


class IndexTests(Base):
    def test_build_and_lookup(self):
        idx = index.build(self.game)
        c = idx["api"]["classes"]
        self.assertEqual(c["PlayerPuppet"]["parent"], "GameObject")
        m = index.find_member(idx, "PlayerPuppet", "RegisterInputListener")
        self.assertEqual(m["owner"], "GameObject")
        ev = index.find_member(idx, "PlayerPuppet", "OnGameAttached")
        self.assertTrue(ev["event"])
        self.assertEqual(ev["ret"], "Bool")
        self.assertIsNotNone(index.find_member(idx, "ScriptableSystem", "OnAttach"))
        self.assertEqual(index.find_member(idx, "PlayerPuppet", "GetHealth")["ret"], "Float")
        self.assertIn("A", idx["api"]["enums"]["EFoo"]["values"])
        self.assertIn("Items.GenericFaceClothing", idx["tweak_records"])
        self.assertIn("Clothing", idx["record_types"].values())
        self.assertTrue(any(r["name"] == "PlayerPuppet" for r in index.search(idx, "playerpup", "class")))
        self.assertTrue(any(g["name"] == "GlobalHelper" for g in idx["api"]["globals"]))

    def test_reds_hooks_indexed(self):
        mod = self.game / "r6/scripts/ModA"
        mod.mkdir(parents=True)
        (mod / "a.reds").write_text("@replaceMethod(PlayerPuppet)\nprotected cb func OnGameAttached() -> Bool {\n  return true;\n}\n"
                                    "@addField(PlayerPuppet)\npublic let modA: Int32;\n", encoding="utf-8")
        idx = index.build(self.game)
        kinds = {(h["kind"], h["member"], h["origin"]) for h in idx["api"]["hooks"]}
        self.assertIn(("replaceMethod", "OnGameAttached", "mod:ModA"), kinds)
        self.assertIn(("addField", "modA", "mod:ModA"), kinds)


class StaticCheckTests(Base):
    def test_hook_targets(self):
        idx = index.build(self.game)
        f = self.tmp / "x.reds"
        f.write_text("@wrapMethod(PlayerPuppet)\nprotected cb func OnGameAttachd() -> Bool { return wrappedMethod(); }\n"
                     "@wrapMethod(PlayerPupet)\nprotected cb func OnAction() -> Bool { return true; }\n"
                     "@wrapMethod(PlayerPuppet)\nprotected cb func OnGameAttached() -> Bool { return wrappedMethod(); }\n"
                     "func F() { while true { continue; } }\n", encoding="utf-8")
        codes = [x["code"] for x in redscript.static_check([f], idx)]
        self.assertIn("RS-NO-METHOD", codes)
        self.assertIn("RS-NO-CLASS", codes)
        self.assertIn("RS-CONTINUE", codes)
        self.assertEqual(codes.count("RS-NO-METHOD"), 1)

    def test_native_only_calls(self):
        idx = index.build(self.game)
        f = self.tmp / "log.reds"
        f.write_text('func A() {\n  LogChannel(n"DEBUG", "x"); // LogChannel(\n  let s = "LogChannel(";\n  GlobalHelper(1);\n}\n',
                     encoding="utf-8")
        found = [(x["code"], x["line"]) for x in redscript.static_check([f], idx)]
        self.assertEqual(found, [("RS-NATIVE-ONLY", 2)])
        # Declaring it yourself is the documented way to call a native.
        own = self.tmp / "decl.reds"
        own.write_text("native func LogChannel(channel: CName, text: script_ref<String>)\n", encoding="utf-8")
        self.assertEqual(redscript.static_check([f, own], idx), [])
        # Declared by an installed mod: compiles here, breaks for players without it.
        mod = self.game / "r6/scripts/LogHeaders"
        mod.mkdir(parents=True)
        (mod / "log.reds").write_text("native func LogChannel(channel: CName, text: script_ref<String>)\n", encoding="utf-8")
        index._CACHE.clear()
        idx = index.build(self.game)
        found = redscript.static_check([f], idx)
        self.assertEqual([x["code"] for x in found], ["RS-NATIVE-VIA-MOD"])
        self.assertIn("LogHeaders", found[0]["message"])
        self.assertEqual(redscript.static_check([f], idx, deps=["logheaders"]), [])

    def test_parse_scc_output(self):
        text = ("[INFO - x] Compiling\n[ERROR - x] [UNRESOLVED_FN] At C:\\g\\r6\\scripts\\MyMod\\a.reds:11:3:\n"
                "  LogChannel(n\"X\", s\"y\");\nfunction 'LogChannel' not found\n[WARN - x] At C:\\g\\r6\\scripts\\Other\\b.reds:1:1:\n"
                "  unused\n[INFO - x] Compilation complete\n")
        r = redscript.parse_scc_output(text, focus="MyMod")
        self.assertEqual(len(r["errors"]), 1)
        self.assertEqual(r["errors"][0]["code"], "UNRESOLVED_FN")
        self.assertEqual(r["errors"][0]["mod"], "MyMod")
        self.assertEqual(r["errors"][0]["line"], 11)
        self.assertTrue(r["complete"])


class ApiDiffTests(Base):
    def store_as(self, name):
        index.build(self.game)
        index._CACHE.clear()
        (self.home / "index" / "unknown").rename(self.home / "index" / name)

    def test_diff_and_affected_hooks(self):
        self.store_as("3.0.80.51928")
        script = self.game / "tools/redmod/scripts/core/player.script"
        text = script.read_text(encoding="utf-8")
        text = text.replace("\tpublic const function GetHealth() : Float\n\t{\n\t\treturn m_health;\n\t}\n", "")
        text = text.replace("protected event OnAction( action : ListenerAction, consumer : ListenerActionConsumer )",
                            "protected event OnAction( action : ListenerAction )")
        text = text.replace("\tB = 1,\n", "") + "\nclass NewThing extends IScriptable\n{\n}\n"
        script.write_text(text, encoding="utf-8")
        tw = self.game / "tools/redmod/tweaks/base/items.tweak"
        tw.write_text(tw.read_text(encoding="utf-8").replace("Preset_Lexington_Default : WeaponItem", "Preset_New : WeaponItem"),
                      encoding="utf-8")
        self.store_as("3.0.88.46235")
        code, v = run_cli("api", "versions")
        self.assertEqual([x["version"] for x in v["stored"]], ["3.0.80.51928", "3.0.88.46235"])
        d = index.diff(index.load_version("3.0.80.51928"), index.load_version("3.0.88.46235"))
        self.assertIn({"class": "PlayerPuppet", "member": "GetHealth", "kind": "func"}, d["members_removed"])
        self.assertEqual([c["member"] for c in d["signatures_changed"]], ["OnAction"])
        self.assertIn("NewThing", d["classes_added"])
        self.assertEqual(d["enum_values_removed"], [{"enum": "EFoo", "values": ["B"]}])
        self.assertEqual(d["tweak_records_removed"], ["Items.Preset_Lexington_Default"])
        self.assertEqual(d["tweak_records_added"], ["Items.Preset_New"])
        out = self.tmp / "proj"
        project.new_project("Hook Mod", ["redscript"], out, "T", "d")
        reds = out / "game/r6/scripts/HookMod/Hooks.reds"
        reds.write_text("@wrapMethod(PlayerPuppet)\npublic const func GetHealth() -> Float {\n  return wrappedMethod();\n}\n",
                        encoding="utf-8")
        code, r = run_cli("api", "diff", "3.0.80.51928", "3.0.88.46235", "--project", str(out))
        self.assertEqual(code, 1)
        self.assertEqual([(h["member"], h["why"]) for h in r["project_hooks_affected"]], [("GetHealth", "method removed")])
        code, r = run_cli("api", "diff", "9.9", "3.0.88.46235")
        self.assertEqual(code, 2)
        self.assertIn("stored", r["error"])


ALL_KINDS = ["redscript", "modsettings", "cet", "tweakxl", "input", "archivexl", "redmod", "audioware", "red4ext"]


class ProjectTests(Base):
    def new(self, kinds=ALL_KINDS, name="Test Mod"):
        out = self.tmp / "proj"
        res = project.new_project(name, kinds, out, "Tester", "desc")
        return out, res

    def test_templates_render_fully(self):
        out, res = self.new()
        self.assertEqual(res["id"], "TestMod")
        for f in util.iter_files(out):
            if f.suffix in (".wav",):
                continue
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("{{", text, f)
            self.assertNotIn("__ID__", str(f))
        m = project.load_manifest(out)
        self.assertEqual(sorted(m["kinds"]), sorted(ALL_KINDS))
        self.assertTrue(any(r["id"] == "red4ext" for r in m["requires"]))

    def test_every_template_kind_exists(self):
        self.assertEqual(sorted(project.templates()), sorted(ALL_KINDS))

    def test_check_passes_on_fresh_project(self):
        out, _ = self.new()
        index.build(self.game)
        r = check.check_project(out)
        self.assertEqual(r["errors"], [], r["errors"])
        gaps = " ".join(g["check"] for g in r["gaps"])
        self.assertIn("redscript compile", gaps)
        self.assertIn("red4ext plugin", gaps)

    def test_check_catches_bad_tweak_and_hook(self):
        out, _ = self.new(["tweakxl", "redscript"])
        index.build(self.game)
        y = out / "game/r6/tweaks/TestMod/TestMod.yaml"
        y.write_text("Items.Bad:\n  $base: Items.DoesNotExist\nItems.Typed:\n  $type: NotAType\n", encoding="utf-8")
        reds = out / "game/r6/scripts/TestMod/TestMod.reds"
        reds.write_text(reds.read_text(encoding="utf-8").replace("OnGameAttached", "OnGameAttachedX"), encoding="utf-8")
        r = check.check_project(out)
        codes = {e["code"] for e in r["errors"]}
        self.assertTrue({"TWEAK-BASE", "TWEAK-TYPE", "RS-NO-METHOD"} <= codes, codes)
        self.assertFalse(r["ok"])

    def test_check_catches_secret_and_version_mirror(self):
        out, _ = self.new(["redmod", "redscript"])
        info = out / "game/mods/TestMod/info.json"
        info.write_text(info.read_text(encoding="utf-8").replace("0.1.0", "9.9.9"), encoding="utf-8")
        reds = out / "game/r6/scripts/TestMod/TestMod.reds"
        reds.write_text(reds.read_text(encoding="utf-8") + "\n// sk-or-v1-" + "a" * 64 + "\n", encoding="utf-8")
        codes = {e["code"] for e in check.check_project(out)["errors"]}
        self.assertIn("SECRET", codes)
        self.assertIn("VERSION-MISMATCH", codes)

    def test_xl_paths_checked_against_built_archive(self):
        out, _ = self.new(["archivexl"])
        arc = out / "game/archive/pc/mod/TestMod.archive"
        archive.write_test_archive(arc, {"testmod\\factories\\testmod.csv": b"x"})
        errs = check.check_project(out)["errors"]
        missing = [e for e in errs if e["code"] == "XL-MISSING"]
        self.assertEqual(len(missing), 1)
        self.assertIn("en-us.json", missing[0]["message"])

    def test_package_is_deterministic_and_clean(self):
        out, _ = self.new(["redscript", "cet", "tweakxl"])
        (out / "game/r6/scripts/TestMod/notes.log").write_text("x", encoding="utf-8")
        a = package.build(out)
        first = Path(a["zip"]).read_bytes()
        b = package.build(out)
        self.assertEqual(first, Path(b["zip"]).read_bytes())
        self.assertTrue(a["validation"]["ok"], a["validation"])
        names = zipfile.ZipFile(a["zip"]).namelist()
        self.assertIn("bin/x64/plugins/cyber_engine_tweaks/mods/TestMod/init.lua", names)
        self.assertFalse(any(n.endswith(".log") or n == "cpforge.json" for n in names))
        self.assertTrue((out / "dist" / "TestMod-0.1.0.receipt.json").is_file())

    def test_validate_flags_bad_zip(self):
        z = self.tmp / "bad.zip"
        with zipfile.ZipFile(z, "w") as zf:
            raw = zipfile.ZipInfo("placeholder")
            raw.filename = "r6\\scripts\\X\\a.reds"  # set after init: ZipInfo normalises it on Windows
            zf.writestr(raw, "x")
            zf.writestr("bin/x64/plugins/cyber_engine_tweaks/mods/Y/other.lua", "x")
            zf.writestr("r6/scripts/X/key.reds", "let k = \"sk-or-v1-" + "b" * 64 + "\";")
            zf.writestr("STATE.md", "x")
            zf.writestr("r6/scripts/A/x.reds", "1")
            zf.writestr("r6/scripts/a/X.reds", "2")
        r = package.validate(z)
        codes = {e["code"] for e in r["errors"]}
        self.assertTrue({"PKG-BACKSLASH", "PKG-SECRET", "PKG-DEV-FILE", "PKG-CET-INIT", "PKG-CASE-DUP"} <= codes, codes)

    def test_bump_updates_mirrors_and_keeps_known_good(self):
        out, _ = self.new(["redmod", "red4ext"])
        package.build(out)
        r = project.bump(out, "minor")
        self.assertEqual(r["new"], "0.2.0")
        self.assertIn('"version": "0.2.0"', (out / "game/mods/TestMod/info.json").read_text(encoding="utf-8"))
        self.assertIn("VERSION 0.2.0", (out / "source/red4ext/CMakeLists.txt").read_text(encoding="utf-8"))
        self.assertIn("## 0.2.0", (out / "CHANGELOG.md").read_text(encoding="utf-8"))
        self.assertTrue((out / "dist/known-good/TestMod-0.1.0.zip").is_file())
        with self.assertRaises(util.ForgeError):
            project.bump(out, "sideways")

    def test_nexus_kit(self):
        out, _ = self.new(["redscript", "tweakxl"])
        (out / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0 - 2026-01-01\n- Adds a thing.\n", encoding="utf-8")
        r = nexus.kit(out)
        desc = (Path(r["folder"]) / "description.bbcode").read_text(encoding="utf-8")
        self.assertIn("[*]Adds a thing.", desc)
        self.assertIn("TweakXL", desc)
        self.assertEqual(r["private_path_in"], [])

    def test_deploy_and_undeploy_restore(self):
        out, _ = self.new(["redscript"])
        target = self.game / "r6/scripts/TestMod/TestMod.reds"
        target.parent.mkdir(parents=True)
        target.write_text("ORIGINAL", encoding="utf-8")
        with self.assertRaises(util.ForgeError):
            deploy.deploy(out, self.game)
        r = deploy.deploy(out, self.game, force=True)
        self.assertEqual(r["backed_up"], 1)
        self.assertIn("wrapMethod", target.read_text(encoding="utf-8"))
        u = deploy.undeploy(out)
        self.assertEqual(target.read_text(encoding="utf-8"), "ORIGINAL")
        self.assertEqual(u["restored"], ["r6/scripts/TestMod/TestMod.reds"])

    def test_undeploy_keeps_files_changed_after_deploy(self):
        out, _ = self.new(["tweakxl"])
        deploy.deploy(out, self.game)
        f = self.game / "r6/tweaks/TestMod/TestMod.yaml"
        f.write_text("edited", encoding="utf-8")
        u = deploy.undeploy(out)
        self.assertEqual(u["kept_changed"], ["r6/tweaks/TestMod/TestMod.yaml"])
        self.assertTrue(f.is_file())


class ConflictTests(Base):
    def test_script_and_archive_and_tweak_conflicts(self):
        for name in ("ModA", "ModB"):
            d = self.game / "r6/scripts" / name
            d.mkdir(parents=True)
            (d / "x.reds").write_text("@replaceMethod(PlayerPuppet)\nprotected cb func OnGameAttached() -> Bool { return true; }\n",
                                      encoding="utf-8")
            archive.write_test_archive(self.game / f"archive/pc/mod/{name}.archive", {"shared\\thing.mesh": b"1", f"{name}\\own": b"2"})
            t = self.game / "r6/tweaks" / name
            t.mkdir(parents=True)
            value = "Quality.Rare" if name == "ModA" else "Quality.Epic"
            (t / "t.yaml").write_text(f"Items.GenericFaceClothing:\n  quality: {value}\n  tags: !append [{name}]\n"
                                      "Vendors.Shop:\n  itemStock:\n    - !append Items.X\n"
                                      "Vehicle.list.list:\n  - !append Vehicle.Y\n", encoding="utf-8")
        idx = index.build(self.game)
        s = conflicts.script_conflicts(idx)
        self.assertEqual(s["replace_conflicts"][0]["mods"], ["ModA", "ModB"])
        a = conflicts.archive_conflicts(self.game)
        self.assertEqual(a["overlaps"][0]["shared_resources"], 1)
        t = conflicts.tweak_conflicts(self.game)
        self.assertEqual([c["field"] for c in t["clashes"]], ["Items.GenericFaceClothing.quality"])
        self.assertEqual(t["records_touched_by_several_mods"], 3)  # clothing, vendor, vehicle list


class LogTests(Base):
    def test_collect_and_explain(self):
        (self.game / "r6/logs/redscript_rCURRENT.log").write_text(
            "[ERROR - t] [UNRESOLVED_REF] At C:\\g\\r6\\scripts\\BadMod\\a.reds:3:1:\n  x\n[INFO - t] done\n", encoding="utf-8")
        cet = self.game / "bin/x64/plugins/cyber_engine_tweaks/mods/LuaMod"
        cet.mkdir(parents=True)
        (cet / "LuaMod.log").write_text("[error] init.lua:3: attempt to index a nil value\n", encoding="utf-8")
        r = logs.collect(self.game)
        self.assertEqual(r["redscript"]["errors"][0]["mod"], "BadMod")
        self.assertTrue(any(e["id"] == "RS-UNRESOLVED-REF" for e in r["redscript"]["explain"]))
        self.assertEqual(r["cet_mod_logs_with_errors"][0]["explain"][0]["id"], "LUA-NIL-INDEX")


class CliTests(Base):
    def test_capabilities_cover_parser(self):
        code, d = run_cli("capabilities")
        self.assertEqual(code, 0)
        names = {c["command"] for c in d["commands"]}
        for n in ("doctor", "plan", "index", "api", "tweak", "check", "compile", "package", "validate", "deploy",
                  "undeploy", "bump", "nexus", "logs", "conflicts", "archive", "hash", "new", "build"):
            self.assertIn(n, names)

    def test_doctor_with_fake_game(self):
        code, d = run_cli("doctor", "--game", str(self.game))
        self.assertEqual(code, 0, d)
        self.assertEqual(d["payload"]["status"], "ok")
        self.assertEqual(d["game"]["root"], str(self.game))

    def test_wolvenkit_found_in_known_folder(self):
        from cpforge import game as G
        saved = {k: os.environ.get(k) for k in ("WOLVENKIT_CLI", "LOCALAPPDATA", "PATH")}
        try:
            os.environ.pop("WOLVENKIT_CLI", None)
            os.environ["PATH"] = str(self.tmp / "empty")
            os.environ["LOCALAPPDATA"] = str(self.tmp / "lad")
            self.assertIsNone(G.find_tool("wolvenkit"))
            exe = self.tmp / "lad/ReverseThis/kit/sandbox/tools/wolvenkit-cli/WolvenKit.CLI.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZ")
            self.assertEqual(Path(G.find_tool("wolvenkit")), exe)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_doctor_missing_game_is_named(self):
        os.environ.pop("CP2077_ROOT", None)
        code, d = run_cli("doctor", "--game", str(self.tmp / "nope"))
        self.assertEqual(code, 0)
        self.assertEqual(d["game"]["status"], "missing")
        code, d = run_cli("doctor", "--game", str(self.tmp / "nope"), "--require-game")
        self.assertEqual(code, 1)

    def test_plan_routes(self):
        cases = {"add a new jacket clothing item": "new-asset", "change weapon damage and price": "tweak-data",
                 "my game crashes after the patch": "debug", "add an imgui overlay window with a hotkey": "cet-lua",
                 "native c++ dll plugin": "native-plugin", "publish to nexus with a changelog": "publish",
                 "make a drivable car with working headlights": "vehicle"}
        for text, route in cases.items():
            code, d = run_cli("plan", text)
            self.assertEqual(d["route"]["id"], route, text)

    def test_api_and_tweak_commands(self):
        self.assertEqual(run_cli("index")[0], 0)
        code, d = run_cli("api", "class", "PlayerPuppet", "--filter", "Attached")
        self.assertEqual(code, 0)
        self.assertEqual(d["chain"][:2], ["PlayerPuppet", "GameObject"])
        code, d = run_cli("tweak", "show", "Items.GenericFaceClothing")
        self.assertEqual(code, 0)
        self.assertEqual(d["type"], "Clothing")
        self.assertIn("GenericFaceClothing : Clothing", d["definition"])
        code, d = run_cli("tweak", "exists", "Character.Judy,Character.Nobody")
        self.assertEqual(code, 1)
        self.assertEqual(d["exists"], {"Character.Judy": True, "Character.Nobody": False})

    def test_named_failure_exit_code(self):
        code, d = run_cli("check", "--project", str(self.tmp))
        self.assertEqual(code, 2)
        self.assertIn("fix", d)


class PayloadTests(unittest.TestCase):
    def test_routes_reference_real_docs_and_templates(self):
        routes = util.load_json(util.KNOWLEDGE_DIR / "routes.json")["routes"]
        tpls = project.templates()
        for r in routes:
            for d in r["docs"]:
                self.assertTrue((util.KNOWLEDGE_DIR / d).is_file(), d)
            for t in r["templates"]:
                self.assertIn(t, tpls)

    def test_template_requirements_are_known_frameworks(self):
        ids = {f["id"] for f in util.load_json(util.KNOWLEDGE_DIR / "frameworks.json")["frameworks"]}
        for name, t in project.templates().items():
            for r in t.get("requires", []):
                self.assertIn(r["id"], ids, name)

    def test_facts_have_tiers(self):
        for k, v in util.load_json(util.KNOWLEDGE_DIR / "facts.json")["facts"].items():
            self.assertIn(v["tier"], ("tool-validated", "source", "docs", "observed"), k)
            self.assertIn("value", v, k)

    def test_error_patterns_compile(self):
        for s in util.load_json(util.KNOWLEDGE_DIR / "errors.json")["signatures"]:
            re.compile(s["pattern"])

    def test_docs_list(self):
        self.assertGreaterEqual(len(knowledge.docs()), 15)


class VersionTests(unittest.TestCase):
    def test_version_mirrors(self):
        cl = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        first = re.search(r"^## \[?(\d+\.\d+\.\d+)", cl, re.M).group(1)
        self.assertEqual(first, __version__)
        self.assertIn(__version__, (ROOT / "STATE.md").read_text(encoding="utf-8"))
        self.assertIn(__version__, (ROOT / "skills/cyberpunk-forge/SKILL.md").read_text(encoding="utf-8"))
        self.assertIn("cpforge.__version__", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
