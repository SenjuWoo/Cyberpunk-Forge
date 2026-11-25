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


def _cn(v):
    return {"$type": "CName", "$storage": "string", "$value": v}


def _path(v, storage="string"):
    return {"DepotPath": {"$type": "ResourcePath", "$storage": storage, "$value": v}, "Flags": "Default"}


def wk_doc(root):
    return {"Header": {"WolvenKitVersion": "9.1.0"}, "Data": {"Version": 195, "RootChunk": root}}


def synthetic_mesh(submeshes=3, entries=("paint", "glass"), local=2, preload=False, chunk_mats=None):
    me = [{"$type": "CMeshMaterialEntry", "index": i, "isLocalInstance": 1, "name": _cn(n)} for i, n in enumerate(entries)]
    mats = [{"$type": "CMaterialInstance"} for _ in range(local)]
    root = {"$type": "CMesh", "materialEntries": me, "externalMaterials": [], "preloadExternalMaterials": [],
            "localMaterialBuffer": {"materials": [] if preload else mats},
            "preloadLocalMaterialInstances": [{"HandleId": str(i + 10), "Data": m} for i, m in enumerate(mats)] if preload else [],
            "renderResourceBlob": {"HandleId": "0", "Data": {"header": {"renderChunkInfos": [{"lodMask": 1}] * submeshes}}},
            "appearances": [{"HandleId": "1", "Data": {"$type": "meshMeshAppearance", "name": _cn("default"),
                                                       "chunkMaterials": [_cn(x) for x in (chunk_mats or ["paint"] * submeshes)]}}]}
    return wk_doc(root)


def synthetic_app(dup_handles=False):
    def appearance(handle_base, buffer_id, name):
        comps = [{"$type": "entMeshComponent", "id": "100", "name": _cn("body"), "mesh": _path("mymod\\meshes\\body.mesh"),
                  "meshAppearance": _cn("default"),
                  "parentTransform": {"HandleId": str(handle_base), "Data": {"$type": "entHardTransformBinding",
                                                                               "bindName": _cn("vehicle_slots"), "slotName": _cn("Base")}}},
                 {"$type": "vehicleLightComponent", "id": "101", "name": _cn("head_left"), "lightType": "Head",
                  "materialZone": "Zero", "parentTransform": {"HandleRefId": str(handle_base)}},
                 {"$type": "entAppearanceProxyMeshComponent", "id": "102", "name": _cn("proxy"),
                  "genericCurveSetOverride": _path("0", "uint64")}]
        return {"HandleId": str(handle_base + 1), "Data": {
            "$type": "appearanceAppearanceDefinition", "name": _cn(name),
            # 'components' mirrors the chunks; its bindings refer to the chunk handles (vanilla has no repeated HandleId).
            "components": [dict(c, parentTransform={"HandleRefId": str(handle_base)}) if "parentTransform" in c else dict(c)
                           for c in comps],
            "proxyMesh": _path("mymod\\meshes\\proxy.mesh"),
            "compiledData": {"BufferId": str(buffer_id), "Data": {"CruidDict": {str(i): c["id"] for i, c in enumerate(comps)},
                                                                   "Chunks": comps}}}}
    a = appearance(1, 0, "red")
    b = appearance(1 if dup_handles else 5, 0 if dup_handles else 1, "blue")
    return wk_doc({"$type": "appearanceAppearanceResource", "appearances": [a, b]})


VANILLA_ANIMS = "base\\animations\\vehicle\\standard\\vehicle\\v_standard2_archer_hella.anims"
VANILLA_DEF_RIG = "base\\vehicles\\standard\\v_standard2_archer_hella\\rig\\v_standard2_archer_hella_01__basic_01.rig"


def synthetic_ent(animset=VANILLA_ANIMS, deformation_rig=VANILLA_DEF_RIG, deps=None):
    def animated(cid, name, rig):
        return {"$type": "entAnimatedComponent", "id": cid, "name": _cn(name), "rig": _path(rig),
                "animations": {"$type": "animAnimSetup", "cinematics": [], "hash": "7081828910115425716",
                               "gameplay": [{"$type": "animAnimSetupEntry", "animSet": _path(animset), "priority": 128}]}}
    chunks = [{"$type": "vehicleCarBaseObject"},
              animated("11", "vehicle_rig", "base\\vehicles\\base_rig\\v_base_x4_337_165_44\\v_base_x4_337_165_44.rig"),
              animated("12", "deformation_rig", deformation_rig)]
    root = {"$type": "entEntityTemplate", "components": [dict(c) for c in chunks[1:]],
            "appearances": [{"$type": "entTemplateAppearance", "name": _cn("car_red"), "appearanceName": _cn("red"),
                             "appearanceResource": _path("mymod\\car.app")}],
            "resolvedDependencies": [_path(d)["DepotPath"] and _path(d) for d in (deps if deps is not None else [animset])],
            "compiledData": {"BufferId": "0", "Data": {"CruidDict": {"0": "0", "1": "11", "2": "12"}, "Chunks": chunks}}}
    return wk_doc(root)


def synthetic_anims(rig):
    return wk_doc({"$type": "animAnimSet", "rig": _path(rig), "animations": []})


class ResourceTests(Base):
    def test_ent_animset_must_embed_the_deformation_rig(self):
        from cpforge import resource as R
        own_rig, own_anims = "mymod\\rig\\car_deformation.rig", "mymod\\anims\\car.anims"
        # Vanilla: the Hella animset embeds the Hella deformation rig (calibrated on 2.5).
        self.assertEqual([w["code"] for w in R.check(synthetic_ent())["warnings"]], [])
        # The Sonata bug: own deformation rig, base car's animset -> wheels drawn at 2*own - base.
        w = R.check(synthetic_ent(deformation_rig=own_rig))["warnings"]
        self.assertEqual([x["code"] for x in w], ["RES-ENT-ANIMSET-RIG"])
        self.assertIn("ship your own copy", w[0]["message"])
        # Own animset copy: its embedded rig is read through the resolver.
        docs = {util.resource_hash(own_anims): synthetic_anims(own_rig)}
        good = R.check(synthetic_ent(animset=own_anims, deformation_rig=own_rig), resolver=docs.get)
        self.assertEqual(good["warnings"], [], good["warnings"])
        self.assertEqual(good["summary"]["animsets"], [{"animset": own_anims, "embedded_rig": own_rig, "components":
                                                        ["vehicle_rig", "deformation_rig"]}])
        docs = {util.resource_hash(own_anims): synthetic_anims(VANILLA_DEF_RIG)}  # copied but rig not changed
        w = R.check(synthetic_ent(animset=own_anims, deformation_rig=own_rig), resolver=docs.get)["warnings"]
        self.assertEqual([x["code"] for x in w], ["RES-ENT-ANIMSET-RIG"])
        # resolvedDependencies must list the animset.
        w = R.check(synthetic_ent(animset=own_anims, deformation_rig=own_rig, deps=["mymod\\other.anims"]),
                    resolver={util.resource_hash(own_anims): synthetic_anims(own_rig)}.get)["warnings"]
        self.assertEqual([x["code"] for x in w], ["RES-ENT-DEPS"])

    def test_mesh_rules(self):
        from cpforge import resource as R
        r = R.check(synthetic_mesh())
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(r["summary"]["submeshes"], 3)
        self.assertEqual(r["summary"]["material_storage"], "localMaterialBuffer")
        self.assertTrue(R.check(synthetic_mesh(preload=True))["ok"])
        codes = lambda d: {e["code"] for e in R.check(d)["errors"]}  # noqa: E731
        self.assertIn("RES-MESH-CHUNKMATS", codes(synthetic_mesh(chunk_mats=["paint", "paint"])))
        self.assertIn("RES-MESH-MATNAME", codes(synthetic_mesh(chunk_mats=["paint", "chrome", "paint"])))
        self.assertIn("RES-MESH-LOCAL-COUNT", codes(synthetic_mesh(local=1)))

    def test_app_rules_and_document_wide_handles(self):
        from cpforge import resource as R
        good = R.check(synthetic_app())
        self.assertTrue(good["ok"], good["errors"])
        app = good["summary"]["detail"][0]
        self.assertEqual(app["lights"], [{"name": "head_left", "light_type": "Head", "material_zone": "Zero",
                                          "bound_to": "vehicle_slots/Base"}])
        self.assertEqual(app["proxy_mesh"], "mymod\\meshes\\proxy.mesh")
        bad = R.check(synthetic_app(dup_handles=True))
        self.assertEqual({e["code"] for e in bad["errors"]}, {"RES-HANDLE-DUP", "RES-BUFFER-DUP"})
        doc = synthetic_app()
        chunks = doc["Data"]["RootChunk"]["appearances"][0]["Data"]["compiledData"]["Data"]
        chunks["CruidDict"]["1"] = "999"
        chunks["Chunks"][2]["genericCurveSetOverride"]["DepotPath"]["$value"] = 0
        codes = {e["code"] for e in R.check(doc)["errors"]}
        self.assertTrue({"RES-CRUID", "RES-PATH-UINT64"} <= codes, codes)
        doc = synthetic_app()
        doc["Data"]["RootChunk"]["appearances"][0]["Data"]["components"].pop()
        self.assertIn("RES-COMPONENTS-CHUNKS", {w["code"] for w in R.check(doc)["warnings"]})
        doc = synthetic_app()
        doc["Data"]["RootChunk"]["appearances"][1]["Data"]["compiledData"]["Data"]["Chunks"][1]["parentTransform"] = {"HandleRefId": "77"}
        self.assertIn("RES-HANDLE-DANGLING", {e["code"] for e in R.check(doc)["errors"]})

    def test_references_resolve_against_project_and_game(self):
        from cpforge import resource as R
        root = self.tmp / "proj/source/archive"
        (root / "mymod/meshes").mkdir(parents=True)
        (root / "mymod/meshes/body.mesh").write_bytes(b"CR2W")
        self.assertEqual(R.project_root_of(root / "mymod/meshes/body.mesh"), root.resolve())
        names = R.tree_hashes(root)
        doc = synthetic_app()
        # A path WolvenKit could not name is stored as its hash.
        h = util.resource_hash("mymod\\meshes\\body.mesh")
        doc["Data"]["RootChunk"]["appearances"][1]["Data"]["compiledData"]["Data"]["Chunks"][0]["mesh"] = _path(str(h), "uint64")
        found, summary = R.reference_check(doc, names, {util.resource_hash("base\\x.mesh"): "basegame.archive"})
        self.assertEqual(summary["in_project"], 1)
        self.assertEqual([f["missing"] for f in found], [["mymod\\meshes\\proxy.mesh"]])
        R.name_hashes(doc, names)
        self.assertIn("mymod\\meshes\\body.mesh", R.check(doc)["summary"]["detail"][1]["meshes"])
        doc["Data"]["RootChunk"]["appearances"][0]["Data"]["proxyMesh"] = _path("base\\vehicles\\gone.mesh")
        doc["Data"]["RootChunk"]["appearances"][1]["Data"]["proxyMesh"] = _path("base\\vehicles\\gone.mesh")
        found, summary = R.reference_check(doc, names, {})
        self.assertEqual(found, [])  # vanilla files reference unshipped base\ paths too
        self.assertEqual(summary["vanilla_paths_not_shipped"], ["base\\vehicles\\gone.mesh"])

    def test_res_cli_on_json_and_unreadable_files(self):
        p = self.tmp / "m.mesh.json"
        p.write_text(json.dumps(synthetic_mesh(chunk_mats=["paint"])), encoding="utf-8")
        q = self.tmp / "x.mesh"
        q.write_bytes(b"CR2W" + b"\0" * 16)
        r = self.tmp / "junk.json"
        r.write_bytes(b"\xc3\x28 not json")
        saved = {k: os.environ.get(k) for k in ("WOLVENKIT_CLI", "PATH", "LOCALAPPDATA", "USERPROFILE")}
        os.environ.pop("WOLVENKIT_CLI", None)
        for k in ("PATH", "LOCALAPPDATA", "USERPROFILE"):
            os.environ[k] = str(self.tmp / "empty")
        try:
            code, d = run_cli("res", "check", str(p), str(q), str(r), "--no-game")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.assertEqual(code, 1)
        res = {Path(x["file"]).name: x for x in d["results"]}
        self.assertEqual([e["code"] for e in res["m.mesh.json"]["errors"]], ["RES-MESH-CHUNKMATS"])
        self.assertEqual(res["x.mesh"]["errors"][0]["code"], "RES-READ")  # CR2W needs WolvenKit, named failure
        self.assertEqual(res["junk.json"]["errors"][0]["code"], "RES-READ")


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

    def test_yaml_flat_on_record_from_tweak_source_only(self):
        # Vehicle.vehicle_list is defined in vanilla .tweak sources but not stored in tweakdb.bin (seen on 2.5).
        (self.game / "tools/redmod/tweaks/base/vehicle_list.tweak").write_text(
            "package Vehicle\n\nvehicle_list\n{\n\tfk< Vehicle >[] list = [];\n}\n", encoding="utf-8")
        out, _ = self.new(["tweakxl"])
        index.build(self.game)
        y = out / "game/r6/tweaks/TestMod/TestMod.yaml"
        y.write_text("Vehicle.vehicle_list.list:\n  - !append Vehicle.v_test\nVehicle.v_test:\n  $base: Character.Judy\n",
                     encoding="utf-8")
        r = check.check_project(out)
        self.assertEqual([w for w in r["warnings"] if w["code"] == "TWEAK-FLAT"], [])
        self.assertEqual(r["errors"], [], r["errors"])

    def test_vehicle_record_paths_and_listing(self):
        out, _ = self.new(["tweakxl"])
        index.build(self.game)
        (self.game / "archive/pc/content").mkdir(parents=True)
        archive.write_test_archive(self.game / "archive/pc/content/basegame.archive", {"base\\vehicles\\x.app": b"1"})
        (out / "source/archive/testmod/vehicles").mkdir(parents=True)
        (out / "source/archive/testmod/vehicles/car.ent").write_bytes(b"CR2W")
        y = out / "game/r6/tweaks/TestMod/TestMod.yaml"
        body = ("Vehicle.v_test:\n  $base: Vehicle.v_standard2_archer_hella_player\n"
                "  entityTemplatePath: testmod\\vehicles\\car.ent\n  appearanceResource: base\\vehicles\\x.app\n"
                "  icon: testmod\\ui\\missing.inkatlas\n")
        y.write_text(body, encoding="utf-8")
        r = check.check_project(out)
        warns = [(w["code"], w["message"].split("'")[1] if w["code"] == "TWEAK-RESOURCE" else "") for w in r["warnings"]]
        self.assertIn(("VEHICLE-NOT-LISTED", ""), warns)
        self.assertEqual([m for c, m in warns if c == "TWEAK-RESOURCE"], ["testmod\\ui\\missing.inkatlas"])
        self.assertIn("tweak resource paths (3)", r["checked"])
        y.write_text(body + "Vehicle.vehicle_list.list:\n  - !append Vehicle.v_test\n", encoding="utf-8")
        self.assertNotIn("VEHICLE-NOT-LISTED", {w["code"] for w in check.check_project(out)["warnings"]})

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

    def test_plan_garment_words_reach_new_asset(self):
        # The README example: a new jacket sold by a vendor needs ArchiveXL as well as TweakXL.
        code, d = run_cli("plan", "add a new jacket to a vendor")
        ids = [d["route"]["id"]] + [a["id"] for a in d["also_relevant"]]
        self.assertIn("new-asset", ids)
        self.assertIn("--kind archivexl", d["scaffold"])
        for text in ("a hoodie for V", "new sneakers", "replace the glasses"):
            self.assertEqual(run_cli("plan", text)[1]["route"]["id"], "new-asset", text)
        self.assertNotEqual(run_cli("plan", "fix the address of a quest marker")[1]["route"]["id"], "new-asset")

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


class DeploySafetyTests(Base):
    def new(self, kinds):
        out = self.tmp / "proj"
        project.new_project("Test Mod", kinds, out, "Tester", "desc")
        return out

    def test_force_never_writes_through_a_hard_link(self):
        # Mod managers deploy by hard link: the game file and the staging file are one inode.
        out = self.new(["redscript"])
        staging = self.tmp / "staging" / "TestMod.reds"
        staging.parent.mkdir()
        staging.write_text("STAGED ORIGINAL", encoding="utf-8")
        target = self.game / "r6/scripts/TestMod/TestMod.reds"
        target.parent.mkdir(parents=True)
        try:
            os.link(staging, target)
        except OSError:
            self.skipTest("hard links are not available here")
        deploy.deploy(out, self.game, force=True)
        self.assertIn("wrapMethod", target.read_text(encoding="utf-8"))
        self.assertEqual(staging.read_text(encoding="utf-8"), "STAGED ORIGINAL")
        deploy.undeploy(out)
        self.assertEqual(target.read_text(encoding="utf-8"), "STAGED ORIGINAL")
        self.assertEqual(staging.read_text(encoding="utf-8"), "STAGED ORIGINAL")

    def test_redeploy_does_not_overwrite_a_file_edited_in_the_game_folder(self):
        out = self.new(["tweakxl"])
        deploy.deploy(out, self.game)
        f = self.game / "r6/tweaks/TestMod/TestMod.yaml"
        f.write_text("EDITED IN THE GAME FOLDER", encoding="utf-8")
        with self.assertRaises(util.ForgeError):
            deploy.deploy(out, self.game)
        self.assertEqual(f.read_text(encoding="utf-8"), "EDITED IN THE GAME FOLDER")
        r = deploy.deploy(out, self.game, force=True)
        self.assertEqual(len(r["changed_backed_up"]), 1)
        self.assertEqual(Path(r["changed_backed_up"][0]).read_text(encoding="utf-8"), "EDITED IN THE GAME FOLDER")
        # An unchanged redeploy, and one where the game copy already equals the project copy, pass.
        deploy.deploy(out, self.game)
        (out / "game/r6/tweaks/TestMod/TestMod.yaml").write_text("SAME", encoding="utf-8")
        f.write_text("SAME", encoding="utf-8")
        deploy.deploy(out, self.game)

    def test_failed_deploy_still_records_what_it_wrote(self):
        out = self.new(["redscript", "tweakxl"])
        blocker = self.game / "r6/tweaks/TestMod"  # a file where the mod needs a folder
        blocker.write_text("in the way", encoding="utf-8")
        with self.assertRaises(util.ForgeError):
            deploy.deploy(out, self.game)
        written = self.game / "r6/scripts/TestMod/TestMod.reds"
        self.assertTrue(written.is_file())
        receipt = util.load_json(out / deploy.RECEIPT)
        self.assertEqual([f["path"] for f in receipt["files"]], ["r6/scripts/TestMod/TestMod.reds"])
        deploy.undeploy(out)
        self.assertFalse(written.exists())
        self.assertFalse(any((self.game / "r6/scripts").rglob("*.cpforge-tmp")))

    def test_undeploy_keeps_the_receipt_when_the_game_folder_is_unreachable(self):
        out = self.new(["tweakxl"])
        deploy.deploy(out, self.game)
        self.game.rename(self.tmp / "moved")
        with self.assertRaises(util.ForgeError):
            deploy.undeploy(out)
        self.assertTrue((out / deploy.RECEIPT).is_file())

    def test_undeploy_names_the_backup_of_a_file_it_left_in_place(self):
        out = self.new(["redscript"])
        target = self.game / "r6/scripts/TestMod/TestMod.reds"
        target.parent.mkdir(parents=True)
        target.write_text("ORIGINAL", encoding="utf-8")
        deploy.deploy(out, self.game, force=True)
        target.write_text("edited after deploy", encoding="utf-8")
        u = deploy.undeploy(out)
        self.assertEqual(u["kept_changed"], ["r6/scripts/TestMod/TestMod.reds"])
        self.assertEqual(Path(u["backups_not_restored"][0]["backup"]).read_text(encoding="utf-8"), "ORIGINAL")


class CompileStagingTests(Base):
    def test_every_script_is_staged_once(self):
        out = self.tmp / "proj"
        project.new_project("Test Mod", ["redscript"], out)
        scripts = out / "game/r6/scripts"
        (scripts / "Other").mkdir()
        (scripts / "Other/TestMod.reds").write_text("// same file name, other folder\n", encoding="utf-8")
        (scripts / "Loose.reds").write_text("// directly in r6/scripts\n", encoding="utf-8")
        self.assertEqual(redscript.project_script_dirs(out), [scripts])
        staged = redscript.stage_sources(redscript.project_script_dirs(out), self.tmp / "stage")
        self.assertEqual(sorted(s.relative_to(scripts).as_posix() for s in staged.values()),
                         ["Loose.reds", "Other/TestMod.reds", "TestMod/TestMod.reds"])
        for target, source in staged.items():
            self.assertEqual(target.read_bytes(), source.read_bytes())
        # Two folders passed separately must not collapse onto one file either.
        staged = redscript.stage_sources([scripts / "Other", scripts / "TestMod"], self.tmp / "stage2")
        self.assertEqual(len(staged), 2)

    def test_keep_folder_is_only_cleared_when_the_forge_made_it(self):
        keep = self.tmp / "keep"
        (keep / "scripts").mkdir(parents=True)
        (keep / "scripts/mine.reds").write_text("not the forge's", encoding="utf-8")
        with self.assertRaises(util.ForgeError):
            redscript.scratch_dir(keep)
        self.assertTrue((keep / "scripts/mine.reds").is_file())
        fresh = self.tmp / "fresh"
        work = redscript.scratch_dir(fresh)
        (work / "scripts/old.reds").write_text("left by the last run", encoding="utf-8")
        redscript.scratch_dir(fresh)
        self.assertFalse((fresh / "scripts/old.reds").exists())


class NamedFailureTests(Base):
    """Ordinary bad input is a finding or a named failure, never exit 3."""

    def new(self, kinds, name="Test Mod", description="desc"):
        out = self.tmp / "proj"
        project.new_project(name, kinds, out, "Tester", description)
        return out

    def test_res_check_without_a_game(self):
        from cpforge import game as G
        os.environ.pop("CP2077_ROOT", None)
        saved, G.candidates = G.candidates, lambda: []
        try:
            p = self.tmp / "x.mesh.json"
            p.write_text(json.dumps(wk_doc(synthetic_mesh())), encoding="utf-8")
            code, d = run_cli("res", "check", str(p))
        finally:
            G.candidates = saved
        self.assertEqual(code, 0, d)
        self.assertIsNone(d["references"]["unresolved"])

    def test_unreadable_index_is_named(self):
        index.build(self.game)
        (index.index_dir(self.game) / "index.json.gz").write_bytes(b"garbage")
        index._CACHE.clear()
        code, d = run_cli("doctor")
        self.assertEqual(code, 0, d)
        self.assertIsNone(d["game"]["index"]["built"])
        code, d = run_cli("api", "search", "Player")
        self.assertEqual(code, 2, d)
        self.assertIn("cpforge index", d["fix"])

    def test_malformed_project_files_are_findings(self):
        cases = (("redmod", "game/mods/TestMod/info.json", "{bad", "REDMOD-INFO"),
                 ("redmod", "game/mods/TestMod/info.json", "[1]", "REDMOD-INFO"),
                 ("archivexl", "game/archive/pc/mod/TestMod.archive.xl", "- a\n- b\n", "XL-YAML"),
                 ("audioware", "game/r6/audioware/TestMod/TestMod.yaml", "- a\n", "AUDIOWARE-YAML"),
                 ("audioware", "game/r6/audioware/TestMod/TestMod.yaml", "sfx:\n  - a\n", "AUDIOWARE-YAML"))
        for kind, relp, body, expected in cases:
            with self.subTest(file=relp, body=body):
                shutil.rmtree(self.tmp / "proj", ignore_errors=True)
                out = self.new([kind])
                (out / relp).write_text(body, encoding="utf-8")
                code, d = run_cli("check", "--project", str(out))
                self.assertEqual(code, 1, d)
                self.assertIn(expected, [e["code"] for e in d["errors"]])

    def test_corrupt_archive_next_to_xl_is_a_finding(self):
        out = self.new(["archivexl"])
        (out / "game/archive/pc/mod/TestMod.archive").write_bytes(b"not an archive at all, but long enough to read a header")
        r = check.check_project(out)
        self.assertIn("XL-ARCHIVE", [e["code"] for e in r["errors"]])

    def test_truncated_tweakdb_is_named(self):
        p = self.game / "r6/cache/tweakdb.bin"
        p.write_bytes(p.read_bytes()[:40])
        code, d = run_cli("tweak", "exists", "Items.X")
        self.assertEqual(code, 2, d)

    def test_new_with_characters_a_folder_cannot_hold(self):
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            code, d = run_cli("new", "Mod: Redux?", "--kind", "tweakxl")
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0, d)
        self.assertEqual(d["id"], "ModRedux")
        self.assertTrue((Path(d["project"]) / "cpforge.json").is_file())

    def test_version_mirror_that_cannot_be_read_is_reported(self):
        out = self.new(["redmod"])
        (out / "game/mods/TestMod/info.json").write_text('{"name": "TestMod", "ver": "9.9.9"}', encoding="utf-8")
        r = check.check_project(out)
        self.assertIn("VERSION-PATTERN", [w["code"] for w in r["warnings"]])
        b = project.bump(out, "minor")
        self.assertEqual([s["path"] for s in b["skipped"]], ["game/mods/TestMod/info.json"])
        (out / "game/mods/TestMod/info.json").unlink()
        r = check.check_project(out)
        self.assertIn("VERSION-FILE-MISSING", [w["code"] for w in r["warnings"]])

    def test_source_secrets_are_scanned_under_a_folder_named_build(self):
        out = self.tmp / "build" / "proj"
        project.new_project("Test Mod", ["redscript"], out)
        (out / "source").mkdir(exist_ok=True)
        (out / "source/notes.txt").write_text("key sk-ant-" + "a" * 30, encoding="utf-8")
        (out / "source/build").mkdir()
        (out / "source/build/gen.txt").write_text("key sk-ant-" + "b" * 30, encoding="utf-8")
        r = check.check_project(out)
        hits = [w["file"] for w in r["warnings"] if w["code"] == "SECRET-SOURCE"]
        self.assertEqual(hits, ["source/notes.txt"])

    def test_stale_tool_variable_does_not_hide_a_tool_on_path(self):
        from cpforge import game as G
        saved_env, saved_which = os.environ.get("CPFORGE_LUA"), shutil.which
        os.environ["CPFORGE_LUA"] = str(self.tmp / "gone" / "luajit.exe")
        shutil.which = lambda name, *a, **k: ("/found/luajit" if name == "luajit" else None)
        try:
            self.assertEqual(G.find_tool("luajit"), "/found/luajit")
        finally:
            shutil.which = saved_which
            if saved_env is None:
                os.environ.pop("CPFORGE_LUA", None)
            else:
                os.environ["CPFORGE_LUA"] = saved_env

    def test_conflicts_without_an_index_still_reports_archives_and_tweaks(self):
        code, d = run_cli("conflicts")
        self.assertEqual(code, 0, d)
        self.assertIn("skipped", d["scripts"])
        self.assertIn("archives", d)
        self.assertIn("tweaks", d)
        code, d = run_cli("conflicts", "--what", "scripts")
        self.assertEqual(code, 2)

    def test_inventory_counts_folders_and_survives_brackets_in_the_path(self):
        from cpforge import game as G
        for name in ("plain", "Games [SSD] (x)"):
            with self.subTest(folder=name):
                g = make_game(self.tmp / name / "Cyberpunk 2077")
                (g / "r6/scripts/ModA").mkdir()
                (g / "r6/scripts/loose.reds").write_text("", encoding="utf-8")
                (g / "r6/scripts/__folder_managed_by_vortex").write_text("", encoding="utf-8")
                (g / "red4ext/logs").mkdir(parents=True)
                (g / "red4ext/logs/red4ext.log").write_text("[error] boom\n", encoding="utf-8")
                s = G.inventory(g)["surfaces"]
                self.assertEqual((s["redscript_mods"], s["redscript_loose_files"]), (1, 1))
                self.assertEqual([x["file"] for x in logs.collect(g)["sources"]], ["red4ext/logs/red4ext.log"])

    def test_names_with_quotes_render_valid_files(self):
        name, desc = 'Bob\'s "Best" Mod', 'Say "hi" \\ there'
        out = self.new(["redmod", "cet", "modsettings", "redscript"], name, desc)
        info = json.loads((out / "game/mods/BobSBestMod/info.json").read_text(encoding="utf-8"))
        self.assertEqual(info["description"], desc)
        lua = (out / "game/bin/x64/plugins/cyber_engine_tweaks/mods/BobSBestMod/init.lua").read_text(encoding="utf-8")
        self.assertIn("ImGui.Begin('Bob\\'s \\\"Best\\\" Mod')", lua)
        reds = (out / "game/r6/scripts/BobSBestMod/BobSBestModSettings.reds").read_text(encoding="utf-8")
        self.assertIn('@runtimeProperty("ModSettings.mod", "Bob\'s \\"Best\\" Mod")', reds)
        self.assertEqual(project.load_manifest(out)["name"], name)
        code, d = run_cli("check", "--project", str(out))
        self.assertNotEqual(code, 3, d)

    def test_adding_a_kind_keeps_the_project_identity(self):
        out = self.new(["redscript"])
        r = project.new_project("Other Name", ["cet", "redmod"], out, force=True)
        self.assertEqual(r["id"], "TestMod")
        self.assertTrue((out / "game/bin/x64/plugins/cyber_engine_tweaks/mods/TestMod/init.lua").is_file())
        self.assertFalse((out / "game/bin/x64/plugins/cyber_engine_tweaks/mods/OtherName").exists())
        project.new_project("Test Mod", ["redmod"], out, force=True)
        self.assertEqual(len(project.load_manifest(out)["version_files"]), 1)

    def test_validate_does_not_inflate_binary_members(self):
        z = self.tmp / "m.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("archive/pc/mod/Big.archive", b"\0" * 4096)
            f.writestr("r6/scripts/M/a.reds", "// ok\n")
        read, saved = [], zipfile.ZipFile.read

        def spy(self_, member, *a, **k):
            read.append(getattr(member, "filename", member))
            return saved(self_, member, *a, **k)
        zipfile.ZipFile.read = spy
        try:
            package.validate(z)
        finally:
            zipfile.ZipFile.read = saved
        self.assertEqual(read, ["r6/scripts/M/a.reds"])


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


@unittest.skipUnless(sys.platform == "win32", "cmd.exe launcher")
class LauncherTests(unittest.TestCase):
    def test_venv_branch_returns_python_exit_code(self):
        # %ERRORLEVEL% inside a parenthesised block is expanded when the block is parsed, so the
        # launcher used to return the errorlevel from before python ran (0) instead of python's.
        import subprocess
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy(ROOT / "cpforge.cmd", tmp / "cpforge.cmd")
        # A venv without cpforge: "-m cpforge" fails with a non-zero exit code.
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(tmp / ".venv")], check=True)
        env = {k: v for k, v in os.environ.items() if k.upper() != "PYTHONPATH"}
        r = subprocess.run(["cmd", "/d", "/c", str(tmp / "cpforge.cmd"), "doctor", "--no-such-flag"],
                           capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
