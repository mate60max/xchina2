#!/usr/bin/env python3

import os
import sys
import queue
import datetime
import urllib.parse
import collections
import errno
import json

from .utils import (
    locked_file,
    read_plain_urls,
    write_plain_urls
)

THIS_CMD = 'xchina2'
DOWNLOAD_COMMON_ARG = ''
ABCM = 5

SourceParam = collections.namedtuple(
    'SourceParam', ['sid', 'extractor', 'output_template', 'url_format', 'todo_urls'])
sp_xc_p = SourceParam(
    sid='xc_p',
    extractor='xchinaphoto',
    output_template='%(uploader)s/%(playlist_title)s-%(playlist_id)s/%(title)s.%(ext)s',
    url_format='https://xchina.co/photo/id-%s.html',
    todo_urls={},
)
sp_xc_v = SourceParam(
    sid='xc_v',
    extractor='xchinavideo',
    output_template='%(uploader)s/%(title)s-%(id)s.%(ext)s',
    url_format='https://xchina.co/video/id-%s.html',
    todo_urls={},
)
sp_xbbs = SourceParam(
    sid='xbbs',
    extractor='xbbsthread',
    output_template='%(playlist_title)s/%(playlist_index)s-%(playlist_id)s.%(ext)s',
    url_format='https://xbbs.me/thread/id-%s.html',
    todo_urls={},
)

MySource = collections.namedtuple('MySource', ['xc_p', 'xc_v', 'xbbs'])
mySource = MySource(
    xc_p=sp_xc_p,
    xc_v=sp_xc_v,
    xbbs=sp_xbbs
)

class ConfigHandler(object):
    ROOT_DIR = './'
    LISTS_FILE = 'lists.txt'
    ITEMS_FILE = 'items.txt'
    FAILED_FILE = 'failed.txt'

    @classmethod
    def setRootDir(self, root_dir='.'):
        self.ROOT_DIR = os.path.abspath(root_dir)
        print(f'[===] Config.root_dir changed to: {self.ROOT_DIR}')

    @classmethod
    def getBinDir(self, work_dir=None):
        if not work_dir:
            work_dir = self.ROOT_DIR
        bin_dir = os.path.join(work_dir, 'bin')
        if not os.path.exists(bin_dir):
            os.makedirs(bin_dir)
        return bin_dir

    @classmethod
    def getConfDir(self, work_dir=None):
        if not work_dir:
            work_dir = self.ROOT_DIR
        conf_dir = os.path.join(work_dir, 'conf')
        if not os.path.exists(conf_dir):
            os.makedirs(conf_dir)
        return conf_dir

    @classmethod
    def getListsFile(self, work_dir=None):
        conf_dir = self.getConfDir(work_dir)
        return os.path.join(conf_dir, self.LISTS_FILE)
    
    @classmethod
    def getItemsFile(self, work_dir=None):
        conf_dir = self.getConfDir(work_dir)
        return os.path.join(conf_dir, self.ITEMS_FILE)
    
    @classmethod
    def getFailedFile(self, work_dir=None):
        conf_dir = self.getConfDir(work_dir)
        return os.path.join(conf_dir, self.FAILED_FILE)
    
class XchinaParser(object):

    POSSIBLE_MODEL_URL_PREFIXS = [
        'https://xchina.co/model/id-',
        'https://xchina.co/photos/model-',
        'https://xchina.co/videos/model-'
    ]

    @classmethod
    def parse_referer(self, url):
        ret = urllib.parse.urlparse(url)
        return f'{ret.scheme}://{ret.netloc}/'

    @classmethod
    def is_model_url(self, url):
        for prefix in self.POSSIBLE_MODEL_URL_PREFIXS:
            if url.startswith(prefix):
                return True
        return False

    @classmethod
    def get_model_id(self, url):
        if not self.is_model_url(url):
            return None

        for prefix in self.POSSIBLE_MODEL_URL_PREFIXS:
            if url.startswith(prefix):
                slash = prefix.rfind('/')
                if slash > len(prefix):
                    return url[len(prefix):slash]
                else:
                    return url[len(prefix):url.rfind('.html')]
        return None

    @classmethod
    def get_model_id_url(self, url):
        if not self.is_model_url(url):
            return None, None
        model_id = self.get_model_id(url)
        if model_id is None:
            return None, None
        return model_id, f'https://xchina.co/model/id-{model_id}.html'

    @classmethod
    def get_model_pv_urls(self, model_id):
        return f'https://xchina.co/photos/model-{model_id}.html', f'https://xchina.co/videos/model-{model_id}.html'

    @classmethod
    def extract_page_end(self, url):
        number = url[url.rfind('/')+1:url.rfind('.')]
        if number.isnumeric():
            prefix = url[:url.rfind('/')]
            return [
                prefix,
                f'{prefix}.html',
                url,
            ]
        else:
            prefix = url[:url.rfind('.')]
            return [
                prefix,
                f'{prefix}.html',
                f'{prefix}/1.html',
            ]
        
    @classmethod
    def append_url_to_list(self, to_list, first, second):
        if first is None:
            if second is not None:
                second = second.strip().replace('\\n', '')
                if len(second) > 0:
                    to_list.append(second)
        else:
            first = first.strip().replace('\\n', '')
            if len(first) > 0:
                to_list.append(first)

class PlaylistArchiveHandler(object):

    @classmethod
    def list_playlist_archive_series_files(self, output_path):
        dir = os.path.dirname(output_path)
        filename = os.path.basename(output_path)
        prefix = f'{filename[:filename.rfind(".")]}_'
        ext = filename[filename.rfind('.'):]
        files = os.listdir(dir)
        ret = []
        for file in files:
            if file.endswith(ext) and file.startswith(prefix):
                ret.append(os.path.join(dir, file))
        return ret

    @classmethod
    def do_generate_playlist_archive_file(self, input_path, output_path, prefix, url_format):
        if not os.path.exists(input_path):
            print(f'[X] Input path not exists: {input_path}')
            return 0
        
        outputs = []
        try:
            with locked_file(input_path, 'r', encoding='utf-8') as input:
                last = ''
                for line in input:
                    if line.startswith(prefix):
                        cid = line[len(prefix)+1:].strip().replace('\\n', '')
                        index = cid.find('_')
                        if index > 0:
                            cid = cid[:index]
                        if cid != last:
                            outputs.append(url_format % (cid))
                            last = cid
        except IOError as ioe:
            if ioe.errno != errno.ENOENT:
                raise
        write_plain_urls(set(outputs), f'{output_path}.curr.txt')

        sub_files = self.list_playlist_archive_series_files(output_path)
        # print(sub_files)
        for file in sub_files:
            outputs.extend(read_plain_urls(file))

        outputs = set(outputs)
        write_plain_urls(outputs, output_path)
        
        return len(outputs)

    @classmethod
    def get_source_archive_path(self, root_path, source_id):
        return f'{root_path}/downloaded_{source_id}.txt'

    @classmethod
    def get_playlist_archive_path(self, root_path, source_id):
        return f'{root_path}/pl_archive_{source_id}.txt'

    @classmethod
    def generate_playlist_archive_files(self, path, sources, sid=None):
        print(f'[==] Start generating playlist archive files')
        for param in sources:
            if not sid is None and sid != param.sid:
                continue
            cnt = self.do_generate_playlist_archive_file(
                        self.get_source_archive_path(path, param.sid),
                        self.get_playlist_archive_path(path, param.sid),
                        param.extractor, 
                        param.url_format
                    )
            print(
                f'[+] Generated - {param.sid} : {cnt} --> {self.get_playlist_archive_path(path, param.sid)}')

    @classmethod
    def get_playlist_archive_urlparam(self, root_path, source_id):
        archive_path = self.get_playlist_archive_path(root_path, source_id)
        return urllib.parse.urlencode({
            'archive': archive_path
        })

class DownloadHandler(object):

    @classmethod
    def generate_download_item(self,
            url,
            output_template=None,
            args=None):
        ret = {
            'url': url
        }
        if output_template:
            ret['ot'] = output_template
        if args:
            ret['args'] = args
        return ret

    @classmethod
    def generate_download_cmd(
            self,
            url,
            output_template,
            referer=None,
            archive=None,
            download_arg_common=None,
            download_args=None):
        if not output_template or not url:
            return 'echo "param err, continue..."\n'
        cmd = f'youtube-dl' \
            + f' "{url}"' \
            + f' --no-progress' \
            + f' --user-agent "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:105.0) Gecko/20100101 Firefox/105.0"' \
            + f' -o "{output_template}"' \
            + (f' --referer "{referer}"' if referer else '') \
            + (f' --download-archive "{archive}"' if archive else '') \
            + (f' {download_arg_common}' if download_arg_common else '')

        if download_args:
            for arg in download_args:
                cmd = cmd + f' {arg}'
        cmd = cmd + ' $@ \n'
        return cmd

    @classmethod
    def generate_bin_scripts(self,
                            root_path, 
                            sources, 
                            download_archive_path=None, 
                            update_pl_archive=True, 
                            script_name_prefix='run',
                            download_arg_common=None):
        # generate scripts
        print(f'[==] Generating exe scripts:')
        # file_suffix = int(datetime.datetime.timestamp(datetime.datetime.utcnow()))
        file_suffix = datetime.datetime.now().strftime("%y%j-%H%M%S")
        bin_path = ConfigHandler.getBinDir()
        script_paths = []

        # this_file_path = os.path.abspath(__file__)
        
        for source in sources:
            if len(source.todo_urls) > 0:
                param_referer = XchinaParser.parse_referer(source.url_format)
                param_download_archive = PlaylistArchiveHandler.get_source_archive_path(ConfigHandler.getConfDir(), source.sid) if not download_archive_path else download_archive_path
                script_filename = f'{script_name_prefix}_{source.sid}_{file_suffix}.sh'
                script_path = os.path.join(bin_path, script_filename)
                script_paths.append(script_path)
                with open(script_path, 'w') as f:
                    f.write('#!/bin/bash\n\nset -x\n\n')
                    cnt = 1
                    #sort to place 'series-' urls before 'model-' to speed up list updating
                    todo_urls = source.todo_urls
                    keys = list(todo_urls.keys())
                    keys.sort(reverse=False)
                    # sorted_urls = {i: todo_urls[i] for i in keys}
                    for key in keys:
                        item = todo_urls[key]
                        f.write(f'echo -e "\\033]0;{script_filename}:[{cnt}/{len(todo_urls)}]\\007"\n')
                        cmd = self.generate_download_cmd(
                            url=item.get('url', None),
                            output_template=item.get('ot', f'{root_path}/{source.sid}/{source.output_template}'),
                            referer=param_referer,
                            archive=param_download_archive,
                            download_arg_common=download_arg_common,
                            download_args=item.get('args', None)
                        )
                        f.write(cmd)
                        if update_pl_archive:
                            f.write(f'xchina2 playlist {source.sid} \n')
                        f.write('\n')
                        cnt += 1
                    f.flush()
                    
                    f.write(f'echo -e "\\033]0;{script_filename}:[finished]\\007"\n')
                    f.write(f'\necho "Finished!!\nGenerated by: {THIS_CMD}" \n')
                print(f'[+] {source.sid}: {len(source.todo_urls)} --> {script_path}')

        print(f'[=] Scripts generated: {len(script_paths)}')
        for sp in script_paths:
            print(f'bash {sp}')
        return script_paths

def sync_urls(urls, work_dir, recent_only=False):
    print(f'[==] Syncing urls with work dir: {work_dir}')

    ROOT_XCHINA = 'https://xchina.co/'
    ROOT_XBBS = 'https://xbbs.me/'

    lists_path = ConfigHandler.getListsFile()
    items_path = ConfigHandler.getItemsFile()
    config_dir = ConfigHandler.getConfDir()
    # load urls
    LISTS_URLS = read_plain_urls(lists_path)
    ITEMS_URLS = read_plain_urls(items_path)
    write_plain_urls(LISTS_URLS, f'{lists_path}.bak')
    write_plain_urls(ITEMS_URLS, f'{items_path}.bak')
    print(f'[=] Read lists from "{lists_path}": {len(LISTS_URLS)}')
    print(f'[=] Read items from "{items_path}": {len(ITEMS_URLS)}')

    lists = []
    items = []
    for list in LISTS_URLS:
        XchinaParser.append_url_to_list(lists, list, list)
    for item in ITEMS_URLS:
        XchinaParser.append_url_to_list(items, item, item)

    # init todo queue
    todo_failed = []
    todo = queue.Queue()
    for url in urls:
        todo.put(url)

    # handle every url in todo queue
    while not todo.empty():
        url = todo.get()
        if url.startswith(ROOT_XCHINA):
            url_r = url[len(ROOT_XCHINA):]
            if url_r.startswith('model/'):
                model_id = XchinaParser.get_model_id(url)
                p_url, v_url = XchinaParser.get_model_pv_urls(model_id)
                todo.put(p_url)
                todo.put(v_url)
            else:
                paged_urls = XchinaParser.extract_page_end(url)
                model_id, model_url = XchinaParser.get_model_id_url(url)
                if url_r.startswith('photos/'):
                    todo_url = paged_urls[1] if recent_only else paged_urls[2]
                    sp_xc_p.todo_urls[todo_url] = DownloadHandler.generate_download_item(
                            f'{todo_url}?{PlaylistArchiveHandler.get_playlist_archive_urlparam(config_dir, sp_xc_p.sid)}'
                            + (f'&abcm={ABCM}' if recent_only else '')
                        )
                    XchinaParser.append_url_to_list(lists, model_url, paged_urls[1])
                elif url_r.startswith('videos/'):
                    todo_url = paged_urls[1] if recent_only else paged_urls[2]
                    sp_xc_v.todo_urls[todo_url] = DownloadHandler.generate_download_item(
                            f'{todo_url}?{PlaylistArchiveHandler.get_playlist_archive_urlparam(config_dir, sp_xc_v.sid)}'
                        )
                    XchinaParser.append_url_to_list(lists, model_url, paged_urls[1])
                elif url_r.startswith('photo/'):
                    sp_xc_p.todo_urls[paged_urls[1]] = DownloadHandler.generate_download_item(
                            paged_urls[1]
                        )
                    XchinaParser.append_url_to_list(items, None, paged_urls[1])
                elif url_r.startswith('video/'):
                    sp_xc_v.todo_urls[paged_urls[1]] = DownloadHandler.generate_download_item(
                            paged_urls[1]
                        )
                    XchinaParser.append_url_to_list(items, None, paged_urls[1])
                else:
                    todo_failed.append(url)
                    print(f'[X] Unsupported "{ROOT_XCHINA}" URL: {url}')
        elif url.startswith(ROOT_XBBS):
            url_r = url[len(ROOT_XBBS):]
            paged_urls = XchinaParser.extract_page_end(url)
            if url_r.startswith('thread/'):
                sp_xbbs.todo_urls[paged_urls[1]] = DownloadHandler.generate_download_item(
                       paged_urls[1]
                    )
                XchinaParser.append_url_to_list(items, None, paged_urls[1])
            elif url_r.startswith('forum/') or url_r.startswith('user/'):
                todo_url = paged_urls[1] if recent_only else paged_urls[2]
                sp_xbbs.todo_urls[todo_url] = DownloadHandler.generate_download_item(
                       f'{todo_url}?{XchinaParser.get_playlist_archive_urlparam(config_dir, sp_xbbs.sid)}'
                    )
                XchinaParser.append_url_to_list(lists, None, paged_urls[1])
            else:
                todo_failed.append(url)
                print(f'[X] Unsupported "{ROOT_XBBS}" URL: {url}')
        else:
            todo_failed.append(url)
            print(f'[X] Unsupported URL: {url}')

    print('[==] Sync finished!')

    # save URLs
    set_lists = set(lists)
    set_items = set(items)
    write_plain_urls(set_lists, lists_path)
    write_plain_urls(set_items, items_path)
    print(f'[+] Saved lists: {len(set_lists)} (+{len(set_lists) - len(LISTS_URLS)}) --> {lists_path}')
    print(f'[+] Saved items: {len(set_items)} (+{len(set_items) - len(ITEMS_URLS)})--> {items_path}')

    return todo_failed

def scan_photos(photo_dir='./xc_p'):
    path = os.path.abspath(photo_dir)
    if not os.path.exists(path):
        print(f'scan path not exists, exiting: {path}')
        exit()
    ret = {
        'img_set_paths': [],
        'no_id_paths': [],
        'no_pvs_paths': [],
        'no_files_paths': [],
        'unknown_files': [],
        'incomp_pvs': [],
        'dup_size': [],
        'dup_id_set': [],
        're_locate_set': [],
        'empty_model_dir': []
    }
    fix = {
        'dup_size': [],
        'incomp_pvs': [],
        'dup_id_set': [],
        're_locate_set': [],
        'empty_model_dir': []
    }
    re_locate_set_prefixs = ['\u56FD\u6A21', '\u53F0\u6A21', '\u6B27\u6A21', '\u6E2F\u6A21', '\u97E9\u6A21', '\u65E5\u6A21']
    img_set_paths = {}
    print(f'[==] Start scanning photos dir: {path}')
    models = os.listdir(path)
    # print(f'[=] Model dirs found: {len(models)}')
    for model in models:
        model_path = os.path.join(path, model)
        if not os.path.isdir(model_path):
            continue

        re_locate_path = None
        for prefix in re_locate_set_prefixs:
            if model.startswith(prefix) and len(model) > len(prefix):
                re_locate_path = os.path.join(path, prefix)
                break

        img_sets = os.listdir(model_path)
        # print(f'[+] Image sets found for model: {len(img_sets)} --> {model}')
        img_set_dir_cnt = 0
        for img_set in img_sets:
            img_set_path = os.path.join(model_path, img_set)
            if not os.path.isdir(img_set_path):
                continue

            img_set_dir_cnt += 1
            ret['img_set_paths'].append(img_set_path)
            
            if re_locate_path:
                ret['re_locate_set'].append(img_set_path)
                fix['re_locate_set'].append({
                    'img_set': img_set,
                    'img_set_path': img_set_path,
                    're_locate_path': re_locate_path
                })

            img_set_path_name = img_set_path[len(path)+1:]
            img_set_id = None
            img_set_ps = 0
            img_set_vs = 0
            if img_set.rfind('-') >= 0:
                img_set_id = img_set[img_set.rfind('-')+1:]
                isp = img_set_paths.get(img_set_id, [])
                isp.append(img_set_path)
                img_set_paths[img_set_id] = isp

                img_set_left = img_set[:img_set.rfind('-')]
                if img_set_left.rfind('-') >= 0:
                    vps = img_set_left[img_set_left.rfind('-')+1:]
                    if vps.find('P') >= 0:
                        ps = vps[:vps.find('P')]
                        img_set_ps = int(ps)
                        if vps.find('V') >= 0:
                            vs = vps[vps.find('P')+1:vps.find('V')]
                            img_set_vs = int(vs)
                    else:
                        ret['no_pvs_paths'].append(img_set_path)
                else:
                    ret['no_pvs_paths'].append(img_set_path)
            else:
                ret['no_id_paths'].append(img_set_path)

            files = os.listdir(img_set_path)
            if files is None or len(files) <= 0:
                ret['no_files_paths'].append(img_set_path)
                continue

            jpgs = []
            mp4s = []
            exts = []
            size_map = {}
            media_cnt = 0
            for file in files:
                file_low = file.lower()
                if file_low.startswith('.'):
                    continue

                if file_low.endswith('.jpg') or file_low.endswith('.jpeg'):
                    jpgs.append(file)
                    media_cnt += 1
                elif file_low.endswith('.mp4'):
                    mp4s.append(file)
                    media_cnt += 1
                elif file_low.endswith('.json') or file_low.endswith('.txt'):
                    continue
                else:
                    exts.append(file)

                filesize = os.path.getsize(os.path.join(img_set_path, file))
                if filesize in size_map:
                    cnt = size_map[filesize]
                    size_map[filesize] = cnt + 1
                else:
                    size_map[filesize] = 1

            if len(exts) > 0:
                ret['unknown_files'].append(f'UN files in IS:{len(exts)} --> {img_set_path_name}')
                for ext in exts:
                    ret['unknown_files'].append(ext)
            if (img_set_ps + img_set_vs) > 0:
                # if (img_set_ps + img_set_vs) - (len(jpgs) + len(mp4s)) > 1:
                if (img_set_ps ) - (len(jpgs)) > 1 or img_set_vs != len(mp4s):
                    ret['incomp_pvs'].append(
                        f'Incomp IS:{len(jpgs)}P{len(mp4s)}V != {img_set_ps}P{img_set_vs}V --> {img_set_path}')
                    fix['incomp_pvs'].append({
                        'id': img_set_id,
                        'img_set_path': img_set_path,
                    })
                    continue

            for key, value in size_map.items():
                if (value > 1 and key < 30000) or (value * 2) >= media_cnt:
                    ret['dup_size'].append(f'dup size:{key}, cnt:{value} --> {img_set_path}')
                    if img_set_id is not None:
                        fix['dup_size'].append({
                            'id': img_set_id,
                            'img_set_path': img_set_path,
                        })

        if img_set_dir_cnt <= 0:
            ret['empty_model_dir'].append(model_path)
            fix['empty_model_dir'].append(model_path)

    for key, value in img_set_paths.items():
        if len(value) > 1:
            ret['dup_id_set'].append({
                key: value
            })
        if len(value) == 2:
            na_v = None
            co_v = None
            if value[0].find('/NA/') >= 0 and value[1].find('/NA/') < 0:
                na_v = value[0]
                co_v = value[1]
            elif value[1].find('/NA/') >= 0 and value[0].find('/NA/') < 0:
                na_v = value[1]
                co_v = value[0]
            if na_v and co_v:
                fix['dup_id_set'].append({
                    'na': na_v,
                    'co': co_v,
                })

    return ret, fix

def scan(dir='./'):
    path = os.path.abspath(dir)

    def print_scan_ret_entry(ret, key):
        print(f'[===] print ret.{key}:')
        for line in ret[key]:
            print(line)

    def do_fix(work_dir, fix, key, source):
        print(f'[===] fixing {key}, todo size: {len(fix[key])}')
        file_suffix = datetime.datetime.now().strftime("%y%j-%H%M%S")
        download_archive_path = os.path.join(ConfigHandler.getConfDir(), 'fix-downloaded.txt')
        script_file = None

        if key == 'dup_size':
            script_file = os.path.join(ConfigHandler.getBinDir(), f'fix_dupsize_{file_suffix}.sh')
            # update: delete image files only, leave dir there for fix-missing script to fix
            with open(script_file, 'w') as f:
                f.write('#!/bin/bash\n\n')
                for todo in fix[key]:
                    # source.todo_urls.append(source.url_format % todo['id'])
                    f.write(f'rm -rf "{todo["img_set_path"]}"/*\n')
                # f.write(f'rm -f "{download_archive_path}"\n')
                f.flush()
            # print(f'[==] Added todo urls:{len(source.todo_urls)}')
        elif key == 'incomp_pvs':
            for todo in fix[key]:
                url = source.url_format % todo['id']
                query = urllib.parse.urlencode({
                    'force_iter': '1'
                })
                source.todo_urls[url] = DownloadHandler.generate_download_item(
                        url=f'{url}?{query}',
                        output_template=f'{todo["img_set_path"]}{source.output_template[source.output_template.rfind("/"):]}'
                    )
            sps = DownloadHandler.generate_bin_scripts(
                work_dir,
                mySource,
                download_archive_path=download_archive_path, 
                update_pl_archive=False,
                script_name_prefix='fix',
                download_arg_common=DOWNLOAD_COMMON_ARG
            )
            print(f'[==] Added todo urls:{len(source.todo_urls)}')
            if os.path.exists(download_archive_path):
                os.remove(download_archive_path)
            # print(f'You may delete the archive file "conf/fix-downloaded.txt" before running the fix script.')
            return sps
        elif key == 're_locate_set' and len(fix[key]) > 0:
            script_file = os.path.join(ConfigHandler.getBinDir(), f'fix_relocate_{file_suffix}.sh')
            with open(script_file, 'w') as f:
                f.write('#!/bin/bash\n\n')
                cnt = 0
                total = len(fix[key])
                mkdirs = {}
                for todo in fix[key]:
                    cnt = cnt + 1
                    if not todo['re_locate_path'] in mkdirs:
                        mkdirs[todo['re_locate_path']] = True
                        f.write(f'mkdir -p "{todo["re_locate_path"]}" \n')

                    target_dir = os.path.join(todo["re_locate_path"], todo["img_set"])
                    f.write(f'if [ ! -d "{target_dir}" ]; then\n')
                    f.write(f'mv "{todo["img_set_path"]}" "{todo["re_locate_path"]}/" && echo "moved [{cnt}/{total}]" \n')
                    f.write(f'else\n')
                    f.write(f'echo "skipped [{cnt}/{total}], target exists: {target_dir}" \n')
                    f.write(f'fi\n\n')
                f.write(f'find "{work_dir}/{source.sid}" -mindepth 1 -maxdepth 1 -type d -empty -delete\n\n')
                f.write('\n\necho "DONE" \n\n')
                f.flush()
        elif key == 'empty_model_dir' and len(fix[key]) > 0:
            script_file = os.path.join(ConfigHandler.getBinDir(), f'fix_emptymodel_{file_suffix}.sh')
            with open(script_file, 'w') as f:
                f.write('#!/bin/bash\n\n')
                # for todo in fix[key]:
                #     f.write(f'rm -rf "{todo}" \n')
                f.write(f'find "{work_dir}/{source.sid}" -type f -name ".DS_Store" -delete\n\n')
                f.write(f'find "{work_dir}/{source.sid}" -mindepth 1 -maxdepth 1 -type d -empty -delete\n\n')
                f.flush()
        elif key == 'dup_id_set' and len(fix[key]) > 0:
            script_file = os.path.join(ConfigHandler.getBinDir(), f'fix_dupid_{file_suffix}.sh')
            with open(script_file, 'w') as f:
                f.write('#!/bin/bash\n\n')
                for todo in fix[key]:
                    f.write(f'mv -f "{todo["na"]}"/* "{todo["co"]}/" && rm -rf "{todo["na"]}" \n')
                f.write(f'find "{work_dir}/{source.sid}" -type f -name ".DS_Store" -delete\n\n')
                f.write(f'find "{work_dir}/{source.sid}" -mindepth 1 -maxdepth 1 -type d -empty -delete\n\n')
                f.flush()

        if script_file:
            print(f'bash {script_file}')
            return [script_file]

    print('[===] Start scan xc_p:')
    ret, fix = scan_photos(os.path.join(path, 'xc_p'))
    print('[===] Comp scan xc_p:')
    with open(os.path.join(ConfigHandler.getConfDir(), 'scan_ret_xc_p.json'), 'w') as f:
        json.dump(ret, f)
    with open(os.path.join(ConfigHandler.getConfDir(), 'scan_fix_xc_p.json'), 'w') as f:
        json.dump(fix, f)
    print(f'[===] Scan xc_p results saved to: {ConfigHandler.getConfDir()}')

    print(f'Found img_sets:{len(ret["img_set_paths"])}')
    # print_scan_ret_entry(ret, 'img_set_paths')
    print_scan_ret_entry(ret, 'no_id_paths')
    # print_scan_ret_entry(ret, 'no_pvs_paths')
    # print_scan_ret_entry(ret, 'no_files_paths')
    # print_scan_ret_entry(ret, 'unknown_files')
    print_scan_ret_entry(ret, 'incomp_pvs')
    print_scan_ret_entry(ret, 'dup_size')
    print_scan_ret_entry(ret, 'dup_id_set')
    print_scan_ret_entry(ret, 're_locate_set')
    print_scan_ret_entry(ret, 'empty_model_dir')


    ###

    # do_fix(path, fix, 'dup_size', mySource.xc_p)

    ### Stage 1, about img set self
    sps = []
    for key in ['dup_id_set', 're_locate_set', 'empty_model_dir']:
        ret = do_fix(path, fix, key, mySource.xc_p)
        if ret:
            sps.extend(ret)
    if len(sps) > 0:
        print(f'[===] Generated {len(sps)} fix scripts for Stage 1.')
        print(f'[===] Before scanning Stage 2, all fixes in Stage 1 MUST be finished.')
        return sps

    ### Stage 2, about media files in img set
    for key in ['incomp_pvs']:
        ret = do_fix(path, fix, key, mySource.xc_p)
        if ret:
            sps.extend(ret)
    if len(sps) > 0:
        print(f'[===] Generated {len(sps)} fix scripts for Stage 2.')
        # print(f'[===] Before scanning Stage 3, all fixes in Stage 2 MUST be finished.')
        return sps

    print(f'[===] No fix scripts generated.')
    return sps

def process_input_urls(work_dir, urls=[], recent_only=False):
    print(f'[==] Processing {len(urls)} URLs:')

    failed_urls = []
    failed_urls.extend(
        sync_urls(urls, work_dir=work_dir, recent_only=recent_only))

    failed_file = ConfigHandler.getFailedFile()
    if len(failed_urls) > 0:
        write_plain_urls(failed_urls, failed_file)
    print(f'[=] Failed URLs: {len(failed_urls)} --> {failed_file}')
    
    sps = DownloadHandler.generate_bin_scripts(work_dir, mySource, download_arg_common=DOWNLOAD_COMMON_ARG)

    print(f'[==] Process Done.')
    return sps

def process_input_files(work_dir, input_files=[], recent_only=False):
    print(f'[==] Processing {len(input_files)} input files:')

    all_urls = []
    for input_file in input_files:
        urls = read_plain_urls(input_file)
        print(f'[+] Got {len(urls)} URLs from file: {input_file}')
        all_urls.extend(urls)
    
    return process_input_urls(work_dir, all_urls, recent_only)

def real_main(argv):
    print('=====XCHINA2=====')
    global THIS_CMD
    THIS_CMD = ' '.join(argv)
    global DOWNLOAD_COMMON_ARG
    global ABCM

    conf_dir = os.path.abspath(os.environ.get('XCHINA2_CONF_DIR', './'))
    work_dir = os.path.abspath(os.environ.get('XCHINA2_DATA_DIR', './'))
    exe_scripts = os.environ.get('XCHINA2_EXE_SCRIPTS', '0')
    youtube_dl_config = os.environ.get('XCHINA_YOUTUBE_DL_CONFIG', None)
    proxy_setting = os.environ.get('XCHINA2_PROXY_SETTING', None)
    abcm = os.environ.get('XCHINA2_ABCM', '5')

    if exe_scripts:
        if exe_scripts == '1' or exe_scripts.lower() == 'true' or exe_scripts.lower() == 'yes':
            exe_scripts = True
        else:
            exe_scripts = False
    else:
        exe_scripts = False
    print(f'[===] ENV:')
    print(f'[=] conf_dir: {conf_dir}')
    print(f'[=] data_dir: {work_dir}')
    print(f'[=] exe_scripts: {"True" if exe_scripts else "False"}')
    print(f'[=] youtube-dl_config: {youtube_dl_config}')
    print(f'[=] proxy_setting: {proxy_setting}')
    print(f'[=] abcm: {abcm}')

    if conf_dir:
        ConfigHandler.setRootDir(conf_dir)

    if youtube_dl_config:
        DOWNLOAD_COMMON_ARG = DOWNLOAD_COMMON_ARG + f' --config-location {youtube_dl_config}'

    if proxy_setting:
        DOWNLOAD_COMMON_ARG = DOWNLOAD_COMMON_ARG + f' --proxy {proxy_setting}'

    if abcm:
        ABCM = int(abcm)

    sps = None
    if len(argv) > 1:
        arg = argv[1].strip()
        print(f'[===] Cmd arg: {arg}')
        if arg == 'help':
            print(f'xchina2 [ $URL | urls.txt | playlist | full | photo | scan | version | help ]')
            exit()
        elif arg == 'version':
            print(f'20230909') ### VERSION HERE ###
        elif arg.startswith("http"):
            print(f'[=] Start with input URL: {arg}')
            sps = process_input_urls(work_dir, [arg])
        elif arg.endswith('.txt'):
            print(f'[=] Start with input file: {arg}')
            sps = process_input_files(work_dir, [arg])
        elif arg.lower() == 'playlist':
            sid = argv[2].strip() if len(argv) > 2 else None
            PlaylistArchiveHandler.generate_playlist_archive_files(ConfigHandler.getConfDir(), mySource, sid)
            print(f'[=] Done.')
            exit()
        elif arg.lower() == 'full':
            print(f'[=] Start updating fully with default input files: {ConfigHandler.getListsFile()}')
            RECENT_ONLY = False # found full sets 
            print(f'[=] Param: recent_only={RECENT_ONLY}')
            PlaylistArchiveHandler.generate_playlist_archive_files(ConfigHandler.getConfDir(), mySource)
            sps = process_input_files(work_dir, [ConfigHandler.getListsFile()], recent_only=RECENT_ONLY)
        elif arg.lower() == 'photo':
            urls = ['https://xchina.co/photos/kind-1.html', 'https://xchina.co/photos/kind-2.html']
            print(f'[=] Start with default URL: {urls}')
            sps = process_input_urls(work_dir, urls, recent_only=True)
        elif arg.lower() == 'scan':
            sps = scan(work_dir)
        elif arg.lower() == 'test':
            print(f'[=] Start TEST')
            print(f'Conf.0: {ConfigHandler.getConfDir()}')
            # ConfigHandler.setRootDir('/Users/toumasakichi/Downloads/tmp')
            print(f'Conf.1: {ConfigHandler.getConfDir()}')
            print(f'Bin.1: {ConfigHandler.getBinDir()}')
        else:
            print(f'[X] Unsupported input arg, exit..')
            exit()
    else:
        print(f'[==] No arg found, using default input files: {ConfigHandler.getListsFile()}')
        ### IMP, TODO, switch mode
        RECENT_ONLY = True #found recent set only
        print(f'[=] Param: recent_only={RECENT_ONLY}')
        PlaylistArchiveHandler.generate_playlist_archive_files(ConfigHandler.getConfDir(), mySource)
        sps = process_input_files(work_dir, [ConfigHandler.getListsFile()], recent_only=RECENT_ONLY)
        #process_input_files(recent_only=False)#try to force re-sync every set & image
    
    if sps and exe_scripts:
        print(f'[===] Starting executing generated scripts: {len(sps)}')
        for sp in sps:
            print(f'[+] Script to exe: {sp}')
            os.system(f'bash {sp}')
        print(f'[===] All scripts done!')

if __name__ == '__main__':
    real_main(sys.argv)
    
