# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from colorama import Fore, Style
from mutagen import mp3, id3, flac, aiff, oggvorbis, oggopus, aac, mp4
from stat import ST_SIZE
from spotify_ripper.utils import *
import os
import sys
import base64

if sys.version_info < (3, 0):
    from mutagen import m4a


class Tags(object):

    def __init__(self, args, audio_file, idx, track, ripper):
        self.args = args
        self.audio_file = audio_file
        self.on_error = 'replace' if args.ascii_path_only else 'ignore'

        self.tags = {}
        self.populate_tags(track, ripper)
        self.override_tags(idx, track, ripper)

    def create_pair(self, _str):
        return (_str, to_ascii(_str, self.on_error))

    def idx_of_total_str(self, _idx, _total):
        if _total > 0:
            return "%d/%d" % (_idx, _total)
        else:
            return "%d" % (_idx)

    def populate_tags(self, track, ripper):
        args = self.args

        album_browser = track.album.browse()
        album_browser.load(args.timeout)

        self.tags['album'] = self.create_pair(track.album.name)
        artists = ", ".join([artist.name for artist in track.artists]) \
            if args.all_artists else track.artists[0].name
        self.tags['artists'] = self.create_pair(artists)
        self.tags['album_artist'] = self.create_pair(track.album.artist.name)
        self.tags['title'] = self.create_pair(track.name)
        self.tags['year'] = track.album.year
        self.tags['disc_idx'] = track.disc
        self.tags['track_idx'] = track.index

        # calculate num of tracks on disc and num of dics
        num_discs = 0
        num_tracks = 0
        for track_browse in album_browser.tracks:
            if (track_browse.disc == track.disc and
                    track_browse.index > track.index):
                num_tracks = track_browse.index
            if track_browse.disc > num_discs:
                num_discs = track_browse.disc

        self.tags['num_discs'] = num_discs
        self.tags['num_tracks'] = num_tracks

        if args.genres is not None:
            genres = ripper.web.get_genres(args.genres, track)
            if genres is not None and genres:
                self.tags['genres'] = (genres, [to_ascii(genre) for genre in genres])

        # cover art image
        self.image = None
        if args.large_cover_art:
            self.image = ripper.web.get_large_coverart(track.link.uri)

        # if we fail, use regular cover size
        if self.image is None:
            self.image = track.album.cover()
            if self.image is not None:
                self.image.load(args.timeout)
                self.image = self.image.data

    def override_tags(self, idx, track, ripper):
        args = self.args
        tag_overrides = args.tag_override if args.tag_override is not None else []

        if args.comment is not None:
            tag_overrides.append("comment=" + args.comment)

        if args.grouping is not None:
            tag_overrides.append("grouping=" + args.grouping)

        overridable_fieldnames = {
            "album", "title", "artists", "album_artist", "year", "num_discs",
            "num_tracks", "comment", "grouping", "genres"
        }

        for override in tag_overrides:
            tokens = override.strip().split("=", 1)

            if len(tokens) != 2:
                continue

            if tokens[0] not in overridable_fieldnames:
                print("cannot override tag: " + tokens[0])
                continue

            override_str = \
                format_track_string(ripper, tokens[1], idx, track)

            if tokens[0] == "genres":
                self.tags[tokens[0]] = ([override_str], [to_ascii(override_str, self.on_error)])
            else:
                self.tags[tokens[0]] = (override_str, to_ascii(override_str, self.on_error))

    def get_field(self, field, use_ascii):
        pair = self.tags.get(field)
        if pair is not None:
            return pair[0] if not use_ascii or self.args.ascii_path_only else pair[1]
        return None

    def save_cover_image(self, embed_image_func):
        args = self.args

        if self.image is not None:
            def write_image(file_name):
                cover_path = os.path.dirname(self.audio_file)
                cover_file = os.path.join(cover_path, file_name)
                if not path_exists(cover_file):
                    with open(enc_str(cover_file), "wb") as f:
                        f.write(self.image)

            if args.cover_file is not None:
                write_image(args.cover_file)
            elif args.cover_file_and_embed is not None:
                write_image(args.cover_file_and_embed)
                embed_image_func(self.image)
            else:
                embed_image_func(self.image)

    def album(self, use_ascii=True):
        return self.get_field("album", use_ascii)

    def title(self, use_ascii=True):
        return self.get_field("title", use_ascii)

    def artists(self, use_ascii=True):
        return self.get_field("artists", use_ascii)

    def album_artist(self, use_ascii=True):
        return self.get_field("album_artist", use_ascii)

    def year(self):
        return str(self.tags.get("year"))

    def num_discs(self):
        return str(self.tags.get("num_discs"))

    def num_tracks(self):
        return str(self.tags.get("num_tracks"))

    def disc_idx(self):
        return str(self.tags.get("disc_idx"))

    def track_idx(self):
        return str(self.tags.get("track_idx"))

    def track_idx_and_total(self):
        return self.idx_of_total_str(self.tags.get("track_idx"),
            self.tags.get("num_tracks"))

    def track_idx_total_pair(self):
        return (self.tags.get("track_idx"), self.tags.get("num_tracks"))

    def disc_idx_and_total(self):
        return self.idx_of_total_str(self.tags.get("disc_idx"),
            self.tags.get("num_discs"))

    def disc_idx_total_pair(self):
        return (self.tags.get("disc_idx"), self.tags.get("num_discs"))

    def comment(self, use_ascii=True):
        return self.get_field("comment", use_ascii)

    def grouping(self, use_ascii=True):
        return self.get_field("grouping", use_ascii)

    def genres(self, use_ascii=True):
        return self.get_field("genres", use_ascii)


class Id3Tags(Tags):

    def __init__(self, args, audio_file, idx, track, ripper):
        super(Id3Tags, self).__init__(args, audio_file, idx, track, ripper)

    def set_tags(self, audio):
        # add ID3 tag if it doesn't exist
        audio.add_tags()

        def embed_image(data):
            audio.tags.add(
                id3.APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc='Front Cover',
                    data=data
                )
            )

        self.save_cover_image(embed_image)

        if self.album() is not None:
            audio.tags.add(id3.TALB(text=[self.album()], encoding=3))

        audio.tags.add(id3.TIT2(text=[self.title()], encoding=3))
        audio.tags.add(id3.TPE1(text=[self.artists()], encoding=3))

        if self.album_artist() is not None:
            audio.tags.add(id3.TPE2(text=[self.album_artist()], encoding=3))

        audio.tags.add(id3.TDRC(text=[self.year()], encoding=3))
        audio.tags.add(id3.TPOS(text=[self.disc_idx_and_total()], encoding=3))
        audio.tags.add(id3.TRCK(text=[self.track_idx_and_total()], encoding=3))

        if self.comment() is not None:
            audio.tags.add(id3.COMM(text=[self.comment()], encoding=3))

        if self.grouping() is not None:
            audio.tags.add(id3.TIT1(text=[self.grouping()], encoding=3))

        if self.genres() is not None:
            tcon_tag = id3.TCON(encoding=3)
            tcon_tag.genres = self.genres()
            audio.tags.add(tcon_tag)

        if self.args.id3_v23:
            audio.tags.update_to_v23()
            audio.save(v2_version=3, v23_sep='/')
            audio.tags.version = (2, 3, 0)
        else:
            audio.save()


# AAC is not well supported
class RawId3Tags(Tags):

    def __init__(self, args, audio_file, idx, track, ripper):
        super(RawId3Tags, self).__init__(args, audio_file, idx, track, ripper)

    def set_tags(self, audio):
        try:
            id3_dict = id3.ID3(self.audio_file)
        except id3.ID3NoHeaderError:
            id3_dict = id3.ID3()

        def embed_image(data):
            id3_dict.add(
                id3.APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,
                    desc='Front Cover',
                    data=data
                )
            )

        self.save_cover_image(embed_image)

        if self.album() is not None:
            id3_dict.add(id3.TALB(text=[self.album()], encoding=3))

        id3_dict.add(id3.TIT2(text=[self.title()], encoding=3))
        id3_dict.add(id3.TPE1(text=[self.artists()], encoding=3))

        if self.album_artist() is not None:
            id3_dict.add(id3.TPE2(text=[self.album_artist()], encoding=3))

        id3_dict.add(id3.TDRC(text=[self.year()], encoding=3))
        id3_dict.add(id3.TPOS(text=[self.disc_idx_and_total()], encoding=3))
        id3_dict.add(id3.TRCK(text=[self.track_idx_and_total()], encoding=3))

        if self.comment() is not None:
            id3_dict.add(id3.COMM(text=[self.comment()], encoding=3))

        if self.grouping() is not None:
            id3_dict.add(id3.TIT1(text=[self.grouping()], encoding=3))

        if self.genres() is not None:
            tcon_tag = id3.TCON(encoding=3)
            tcon_tag.genres = self.genres()
            id3_dict.add(tcon_tag)

        if self.args.id3_v23:
            id3_dict.update_to_v23()
            id3_dict.save(self.audio_file, v2_version=3, v23_sep='/')
            id3_dict.version = (2, 3, 0)
        else:
            id3_dict.save(self.audio_file)
        audio.tags = id3_dict


class VorbisTags(Tags):

    def __init__(self, args, audio_file, idx, track, ripper):
        super(VorbisTags, self).__init__(args, audio_file, idx, track, ripper)

    def set_tags(self, audio):
        # add Vorbis comment block if it doesn't exist
        if audio.tags is None:
            audio.add_tags()

        def embed_image(data):
            pic = flac.Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Front Cover"
            pic.data = data
            if self.args.output_type == "flac":
                audio.add_picture(pic)
            else:
                data = base64.b64encode(pic.write())
                audio["METADATA_BLOCK_PICTURE"] = [data.decode("ascii")]

        self.save_cover_image(embed_image)

        if self.album() is not None:
            audio.tags["ALBUM"] = self.album()

        audio.tags["TITLE"] = self.title()
        audio.tags["ARTIST"] = self.artists()

        if self.album_artist() is not None:
            audio.tags["ALBUMARTIST"] = self.album_artist()

        audio.tags["DATE"] = self.year()
        audio.tags["YEAR"] = self.year()
        audio.tags["DISCNUMBER"] = self.disc_idx()
        audio.tags["DISCTOTAL"] = self.num_discs()
        audio.tags["TRACKNUMBER"] = self.track_idx()
        audio.tags["TRACKTOTAL"] = self.num_tracks()

        if self.comment() is not None:
            audio.tags["COMMENT"] = self.comment()

        if self.grouping() is not None:
            audio.tags["GROUPING"] = self.grouping()

        if self.genres() is not None:
            audio.tags["GENRE"] = ", ".join(self.genres())

        audio.save()


# only called by Python 3
class MP4Tags(Tags):

    def __init__(self, args, audio_file, idx, track, ripper):
        super(MP4Tags, self).__init__(args, audio_file, idx, track, ripper)

    def set_tags(self, audio):
        # add MP4 tags if it doesn't exist
        if audio.tags is None:
            audio.add_tags()

        def embed_image(data):
            audio.tags["covr"] = mp4.MP4Cover(data)

        self.save_cover_image(embed_image)

        if self.album() is not None:
            audio.tags["\xa9alb"] = self.album()

        audio["\xa9nam"] = self.title()
        audio.tags["\xa9ART"] = self.artists()

        if self.album_artist() is not None:
            audio.tags["aART"] = self.album_artist()

        audio.tags["\xa9day"] = self.year()
        audio.tags["disk"] = [self.disc_idx_total_pair()]
        audio.tags["trkn"] = [self.track_idx_total_pair()]

        if self.comment() is not None:
            audio.tags["\xa9cmt"] = self.comment()

        if self.grouping() is not None:
            audio.tags["\xa9grp"] = self.grouping()

        if self.genres() is not None:
            audio.tags["\xa9gen"] = ", ".join(self.genres())

        audio.save()


class M4ATags(Tags):

    def __init__(self, args, audio_file, idx, track, ripper):
        super(M4ATags, self).__init__(args, audio_file, idx, track, ripper)

    def set_tags(self, audio):
        # add M4A tags if it doesn't exist
        audio.add_tags()

        def embed_image(data):
            audio.tags[str("covr")] = m4a.M4ACover(data)

        self.save_cover_image(embed_image)

        if self.album() is not None:
            audio.tags[b"\xa9alb"] = self.album()

        audio[b"\xa9nam"] = self.title()
        audio.tags[b"\xa9ART"] = self.artists()

        if self.album_artist() is not None:
            audio.tags[str("aART")] = self.album_artist()

        audio.tags[b"\xa9day"] = self.year()
        audio.tags[str("disk")] = self.disc_idx_total_pair()
        audio.tags[str("trkn")] = self.track_idx_total_pair()

        if self.comment() is not None:
            audio.tags[b"\xa9cmt"] = self.comment()

        if self.grouping() is not None:
            audio.tags[b"\xa9grp"] = self.grouping()

        if self.genres() is not None:
            audio.tags[b"\xa9gen"] = ", ".join(self.genres())

        audio.save()


def set_metadata_tags(args, audio_file, idx, track, ripper):
    # log completed file
    print(Fore.GREEN + Style.BRIGHT + os.path.basename(audio_file) +
          Style.NORMAL + "\t[ " +
          format_size(os.stat(enc_str(audio_file))[ST_SIZE]) + " ]" +
          Fore.RESET)

    if args.output_type == "wav" or args.output_type == "pcm":
        print_yellow("Skipping metadata tagging for " + args.output_type +
            " encoding...")
        return

    # ensure everything is loaded still
    if not track.is_loaded:
        track.load(args.timeout)
    if not track.album.is_loaded:
        track.album.load(args.timeout)

    # use mutagen to update audio file tags
    try:
        audio = None
        tags = None

        if args.output_type == "flac":
            audio = flac.FLAC(audio_file)
            tags = VorbisTags(args, audio_file, idx, track, ripper)
            tags.set_tags(audio)

        elif args.output_type == "aiff":
            audio = aiff.AIFF(audio_file)
            tags = Id3Tags(args, audio_file, idx, track, ripper)
            tags.set_tags(audio)

        elif args.output_type == "ogg":
            audio = oggvorbis.OggVorbis(audio_file)
            tags = VorbisTags(args, audio_file, idx, track, ripper)
            tags.set_tags(audio)

        elif args.output_type == "opus":
            audio = oggopus.OggOpus(audio_file)
            tags = VorbisTags(args, audio_file, idx, track, ripper)
            tags.set_tags(audio)

        elif args.output_type == "aac":
            audio = aac.AAC(audio_file)
            tags = RawId3Tags(args, audio_file, idx, track, ripper)
            tags.set_tags(audio)

        elif args.output_type == "m4a" or args.output_type == "alac.m4a":
            if sys.version_info >= (3, 0):
                audio = mp4.MP4(audio_file)
                tags = MP4Tags(args, audio_file, idx, track, ripper)
                tags.set_tags(audio)
            else:
                audio = m4a.M4A(audio_file)
                tags = M4ATags(args, audio_file, idx, track, ripper)
                tags.set_tags(audio)
                audio = mp4.MP4(audio_file)

        elif args.output_type == "mp3":
            audio = mp3.MP3(audio_file, ID3=id3.ID3)
            tags = Id3Tags(args, audio_file, idx, track, ripper)
            tags.set_tags(audio)

        # utility functions
        def bit_rate_str(bit_rate):
            brs = "%d kb/s" % bit_rate
            if not args.cbr:
                brs = "~" + brs
            return brs

        def mode_str(mode):
            modes = ["Stereo", "Joint Stereo", "Dual Channel", "Mono"]
            return modes[mode] if mode < len(modes) else ""

        def channel_str(num):
            channels = ["", "Mono", "Stereo"]
            return channels[num] if num < len(channels) else ""

        def print_line():
            print("-" * 79)

        # log tags
        print_line()
        print_yellow("Setting artist: " + tags.artists())

        if tags.album() is not None:
            print_yellow("Setting album: " + tags.album())

        if tags.album_artist() is not None:
            print_yellow("Setting album artist: " + tags.album_artist())

        print_yellow("Setting title: " + tags.title())
        print_yellow("Setting track info: (" + tags.track_idx() + ", " +
            tags.num_tracks() + ")")
        print_yellow("Setting disc info: (" + tags.disc_idx() + ", " +
            tags.num_discs() + ")")
        print_yellow("Setting release year: " + tags.year())

        if tags.genres() is not None:
            print_yellow("Setting genres: " + " / ".join(tags.genres()))

        if tags.image is not None:
            print_yellow("Adding cover image")

        if tags.comment() is not None:
            print_yellow("Adding comment: " + tags.comment())

        if tags.grouping() is not None:
            print_yellow("Adding grouping: " + tags.grouping())

        # log bitrate info
        if args.output_type == "flac":
            bit_rate = ((audio.info.bits_per_sample * audio.info.sample_rate) *
                        audio.info.channels)
            print("Time: " + format_time(audio.info.length) +
                  "\tFree Lossless Audio Codec" +
                  "\t[ " + bit_rate_str(bit_rate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print_line()
            print_yellow("Writing Vorbis comments - " +
                  audio.tags.vendor)
            print_line()

        elif args.output_type == "aiff":
            print("Time: " + format_time(audio.info.length) +
                  "\tAudio Interchange File Format" +
                  "\t[ " + bit_rate_str(audio.info.bitrate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print_line()
            id3_version = "v%d.%d" % (
                audio.tags.version[0], audio.tags.version[1])
            print("ID3 " + id3_version + ": " +
                  str(len(audio.tags.values())) + " frames")
            print(
                Fore.YELLOW + "Writing ID3 version " +
                id3_version)
            print_line()

        elif args.output_type == "alac.m4a":
            bit_rate = ((audio.info.bits_per_sample * audio.info.sample_rate) *
                        audio.info.channels)
            print("Time: " + format_time(audio.info.length) +
                  "\tApple Lossless" +
                  "\t[ " + bit_rate_str(bit_rate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print_line()
            print_yellow("Writing Apple iTunes metadata")
            print_line()

        elif args.output_type == "ogg":
            print("Time: " + format_time(audio.info.length) +
                  "\tOgg Vorbis Codec" +
                  "\t[ " + bit_rate_str(audio.info.bitrate / 1000) + " @ " +
                  str(audio.info.sample_rate) +
                  " Hz - " + channel_str(audio.info.channels) + " ]")
            print_line()
            print_yellow("Writing Vorbis comments - " +
                  audio.tags.vendor)
            print_line()

        elif args.output_type == "opus":
            print("Time: " + format_time(audio.info.length) + "\tOpus Codec" +
                  "\t[ " + channel_str(audio.info.channels) + " ]")
            print_line()
            print_yellow("Writing Vorbis comments - " +
                  audio.tags.vendor)
            print_line()

        elif args.output_type == "mp3":
            print("Time: " + format_time(audio.info.length) + "\tMPEG" +
                  str(audio.info.version) +
                  ", Layer " + ("I" * audio.info.layer) + "\t[ " +
                  bit_rate_str(audio.info.bitrate / 1000) +
                  " @ " + str(audio.info.sample_rate) + " Hz - " +
                  mode_str(audio.info.mode) + " ]")
            print_line()
            id3_version = "v%d.%d" % (
                audio.tags.version[0], audio.tags.version[1])
            print("ID3 " + id3_version + ": " +
                  str(len(audio.tags.values())) + " frames")
            print_yellow("Writing ID3 version " + id3_version)
            print_line()

        elif args.output_type == "aac":
            print("Time: " + format_time(audio.info.length) +
                  "\tAdvanced Audio Coding" +
                  "\t[ " + bit_rate_str(audio.info.bitrate / 1000) +
                  " @ " + str(audio.info.sample_rate) + " Hz - " +
                  channel_str(audio.info.channels) + " ]")
            print_line()
            id3_version = "v%d.%d" % (
                audio.tags.version[0], audio.tags.version[1])
            print("ID3 " + id3_version + ": " +
                  str(len(audio.tags.values())) + " frames")
            print("Writing ID3 version " + id3_version)
            print_line()

        elif args.output_type == "m4a":
            bit_rate = ((audio.info.bits_per_sample * audio.info.sample_rate) *
                        audio.info.channels)
            print("Time: " + format_time(audio.info.length) +
                  "\tMPEG-4 Part 14 Audio" +
                  "\t[ " + bit_rate_str(bit_rate / 1000) +
                  " @ " + str(audio.info.sample_rate) + " Hz - " +
                  channel_str(audio.info.channels) + " ]")
            print_line()
            print_yellow("Writing Apple iTunes metadata - " +
                  str(audio.info.codec))
            print_line()

    except id3.error:
        print_yellow("Warning: exception while saving id3 tag: " +
              str(id3.error))
