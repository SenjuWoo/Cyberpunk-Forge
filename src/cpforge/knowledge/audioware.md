# Audioware (custom audio)

Audio files plus a YAML manifest in `r6/audioware/<Mod>/`. Layout taken from
installed Audioware mods:

```yaml
version: 1.0.0
sfx:
  mymod_hello:
    file: hello.wav
    settings:
      volume: 1.0
```

The key (`mymod_hello`) is the event name. Prefix it with your mod id so it
cannot clash with other mods. `cpforge check` parses the manifest and warns
when a listed file is missing. How to trigger the sound from redscript depends
on the Audioware version: read its documentation before writing the call.
Nexus: https://www.nexusmods.com/cyberpunk2077/mods/12001
