# REDmod (official loader)

`mods/<Mod>/info.json` (`name`, `version`, optional `description`,
`customSounds` for audio) with `archives/`, `scripts/`, `tweaks/`,
`customSounds/` subfolders. Players need the free REDmod DLC and must deploy
mods from the launcher; deployed state is in `r6/cache/modded/mods.json`.

The REDmod DLC also installs the vanilla script source
(`tools/redmod/scripts`), TweakDB source (`tools/redmod/tweaks`) and a native
RTTI dump (`tools/redmod/metadata.json`). The forge indexes those for
`cpforge api` and `cpforge tweak`, which is why installing REDmod is worth it
even if you never ship a REDmod package.

Prefer redscript and TweakXL: REDmod script and tweak overrides replace whole
vanilla files, so two REDmods touching one file conflict completely.
