import requests
import textwrap

from sphinxcontrib.needs.services.base import BaseService

# Additional needed options, which are not defined by default
EXTRA_DATA_OPTIONS = ['user', 'created_at', 'updated_at', 'closed_at']
EXTRA_LINK_OPTIONS = ['url']
EXTRA_IMAGE_OPTIONS = ['avatar']

# Additional options, which are used to configure the service and shall not be part of the later needs
CONFIG_OPTIONS = ['type', 'query', 'max_amount', 'max_content_lines', 'id_prefix']

# All Github related data options
GITHUB_DATA = ['status', 'tags'] + EXTRA_DATA_OPTIONS + EXTRA_LINK_OPTIONS + EXTRA_IMAGE_OPTIONS

# Needed for layout. Example: "user","avatar",...
GITHUB_DATA_STR = '"' + '","'.join(EXTRA_DATA_OPTIONS + EXTRA_LINK_OPTIONS + EXTRA_IMAGE_OPTIONS) + '"'
CONFIG_DATA_STR = '"' + '","'.join(CONFIG_OPTIONS) + '"'

GITHUB_LAYOUT = {
    'grid': 'complex',
    'layout': {

        'head_left': [
            '<<meta_id()>>',
        ],
        'head': [
            '**<<meta("title")>>**',
        ],
        'head_right': [
            f'<<image("field:avatar", width="40px", align="middle", is_external=True)>>',
            '<<meta("user")>>'
        ],
        'meta_left': [f'<<meta("{x}", prefix="{x}: ")>>' for x in EXTRA_DATA_OPTIONS] +
                     [f'<<link("{x}", text="Link", prefix="{x}: ", is_dynamic=True)>>' for x in EXTRA_LINK_OPTIONS],
        'meta_right': [
            '<<meta("type_name", prefix="type: ")>>',
            f'<<meta_all(no_links=True, exclude=["layout","style",{GITHUB_DATA_STR}, {CONFIG_DATA_STR}])>>',
            '<<meta_links_all()>>'
        ],
        'footer_left': [
            'layout: <<meta("layout")>>',
        ],
        'footer': [
        ],
        'footer_right': [
            'style: <<meta("style")>>'
        ]
    }
}


class GithubService(BaseService):
    options = CONFIG_OPTIONS + EXTRA_DATA_OPTIONS + EXTRA_LINK_OPTIONS + EXTRA_IMAGE_OPTIONS

    def __init__(self, app, name, config, **kwargs):
        self.app = app
        self.name = name
        self.config = config

        self.url = self.config.get('url', 'https://api.github.com/')
        self.need_type = self.config.get('need_type', self.app.config.needs_types[0]['directive'])
        self.max_amount = self.config.get('max_amount', 5)
        self.max_content_lines = self.config.get('max_content_lines', -1)
        self.id_prefix = self.config.get('id_prefix', 'GITHUB_')
        self.layout = self.config.get('layout', 'github')

        if 'github' not in self.app.config.needs_layouts.keys():
            self.app.config.needs_layouts['github'] = GITHUB_LAYOUT

        self.type_config = {
            'issue': {
                'url': 'search/issues',
                'query': 'is:issue',
            },
            'pr': {
                'url': 'search/issues',
                'query': 'is:pr',
            },
            'commit': {
                'url': 'search/commits',
                'query': '',
            },
        }

        if 'type' in kwargs:
            self.type = kwargs['type']

        if self.type not in self.type_config.keys():
            raise KeyError(f'github type "{self.type}" not supported. Use: {", ".join(self.type_config.keys())}')

        super(GithubService, self).__init__()

    def _send(self, query, options):
        query = f'{query} {self.type_config[self.type]["query"]}'
        params = {
            'q': query,
            'per_page': options.get('max_amount', self.max_amount)
        }
        url = self.url + self.type_config[self.type]['url']

        self.log.info(f'Service {self.name} requesting data for query: {query}')
        resp = requests.get(url, params=params)
        return resp.json()

    def request(self, options=None):
        if options is None:
            options = {}
        self.log.debug(f'Requesting data for service {self.name}')

        if 'query' not in options:
            raise NeedGithubServiceException('"query" missing as option for github service.')
        else:
            query = options['query']

        response = self._send(query, options)
        data = []
        for item in response['items']:
            # wraps content lines, if they are too long. Respects already existing newlines.
            content_lines = ['\n   '.join(textwrap.wrap(line, 60, break_long_words=True, replace_whitespace=False))
                             for line in item["body"].splitlines() if line.strip() != '']

            content = '\n\n   '.join(content_lines)
            # Reduce content length, if requested by config
            if self.max_content_lines > 0:
                max_lines = int(options.get('max_content_lines', self.max_content_lines))
                content_lines = content.splitlines()
                if len(content_lines) > max_lines:
                    content_lines = content_lines[0:max_lines]
                    content_lines.append('\n   [...]\n')  # Mark, if content got cut
                content = '\n'.join(content_lines)

            # Be sure the content gets not interpreted as rst or html code, so we put
            # everything in a safe code-block
            content = '.. code-block:: text\n\n   ' + content

            prefix = options.get('id_prefix', self.id_prefix)
            need_id = f'{prefix}{item["number"]}'
            element_data = {
                'type': options.get('type', self.need_type),
                'layout': options.get('layout', self.layout),
                'id': need_id,
                'title': item["title"],
                'content': content,
                'status': item["state"],
                'tags': ",".join([x['name'] for x in item["labels"]]),
                'user': item["user"]['login'],
                'url': item['html_url'],
                'avatar': item['user']['avatar_url'],
                'created_at': item['created_at'],
                'updated_at': item['updated_at'],
                'closed_at': item['closed_at']
            }

            # Add data from options, which was defined by user but is not set by this service
            for key, value in options.items():
                # Check if given option is not already handled and is not part of the service internal options
                if key not in element_data.keys() and key not in GITHUB_DATA:
                    element_data[key] = value

            data.append(element_data)

        return data


class NeedGithubServiceException(BaseException):
    pass