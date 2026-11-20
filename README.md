# CommunityDragon Toolbox

A toolbox to work with League of Legends game files and export files for CDragon.
It can be used as a library or a command-line tool.

Most things are discussed on our [Discord server](https://discord.gg/rZQwuek). Feel free to join!

## Install

```
pip3 install cdtb
```

**Windows users:** if needed precompiled packages of binary dependencies can be found [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/).


## Updating hashes

Most commands require hash lists which are updated frequently and and not bundled with this code.

To download them locally from `raw.communitydragon.org`, run:
```
cdtb fetch-hashes
```

The command will print where they are downloaded.
By default, they will land in `~/.local/share/cdragon` (or `%LOCALAPPDATA%/cdragon` on Windows).
An alternate location can be configured using the `CDTB_HASHES_DIR` or `CDRAGON_DATA` environment variables.

Hashes are versionned in the [Data](https://github.com/CommunityDragon/Data) repository.


## Command-line examples

The CLI interface allows:
 - download game files and list relations between
 - list and extract content of WAD files
 - export game files to be served by CDragon

Here are some examples, use `cdtb -h` for details.

```sh
# download and extract files for the latest patch to the directory `cdn`
# (files from the new patcher will be used)
cdtb -v download -s cdn patch=

# download and extract files from the PBE to the directory `cdn`
cdtb -v download -s cdn --patchline pbe patch=main

# same, but don't download language-specific files
cdtb download -s cdn --no-lang patch=

# list patch versions (using already downloaded data in `cdn/`)
cdtb versions -s cdn patch

# list game files for patch 9.9
cdtb files -s cdn game=9.9

# extract a WAD file
cdtb wad-extract path/to/assets.wad

# list content of a WAD file
cdtb wad-list path/to/assets.wad

# export files from PBE
cdtb export -s cdn --patchline pbe --full main

# export files of patch 7.23 into export/7.23 (deprecated)
cdtb export -o export 7.23
```

## WAD files

WADs are archives used by the clients. They contain assets, game data (e.g.
item description), files for the LCU interface and more.

Paths of files in WAD files are hashed, they are not stored in clear in the
archive. A large number of these hashes have been guessed but there are still a
lot of unresolved hashes.

An hash list is provided and regularly updated with new hashes as they are
discovered, especially after client updates.


## Unreal files (standalone TFT client)

The standalone TFT client is built on Unreal Engine. Its files are stored in
`.pak` files and IoStore containers (a `.utoc` index with `.ucas` data) under
`TFT/Content/Paks/`, instead of WADs. Paths are stored in clear, so no hash
lists are needed, but containers are usually encrypted with an AES-256 key
and compressed with Oodle.

Oodle has no Python implementation. Set `CDTB_OODLE_LIB` to a shared library
that provides it: Epic's `oo2core` library, or a build of the open-source
[ooz](https://github.com/zao/ooz) (`libooz`).

```sh
export CDTB_AES_KEY=0x0123...   # 64 hex digits
export CDTB_OODLE_LIB=/path/to/libooz.so

# list files of a container (a .pak, or the .utoc/.ucas of an IoStore container)
cdtb ue-list TFT/Content/Paks/pakchunk1-WindowsClient.utoc

# extract files matching a pattern
cdtb ue-extract -o out -p 'TFT/Plugins/GameFeatures/Set_19/*' TFT/Content/Paks/pakchunk1-WindowsClient.utoc

# extract English string tables, then dump them as one JSON file
cdtb ue-extract -o out -p '*/en-US/*.locres' TFT/Content/Paks/pakchunk0-WindowsClient.pak
cdtb ue-extract -o out -p '*/en-US/*.locres' TFT/Content/Paks/pakchunk1-WindowsClient.pak
cdtb locres-dump -o strings.json out/TFT/Content/Localization/Game/en-US/Game.locres \
    out/TFT/Content/Localization/Game_locchunk1/en-US/Game_locchunk1.locres
```
