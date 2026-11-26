"""Executado no contêiner: cria perfis locais sem alterar perfis existentes."""
import json
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

INSTRUCOES = '''Entregue o que foi solicitado. Para tarefas de projeto, confirme a pasta de trabalho e consulte instruções e arquivos relevantes. Estabeleça critérios proporcionais ao pedido.
Antes de editar, leia o conteúdo necessário. Se uma edição falhar, releia o arquivo e a mensagem de erro; não inclua números de linha ou outros marcadores da ferramenta no texto original. Não repita a mesma tentativa sem mudar de estratégia.
Verifique as alterações e execute verificações proporcionais capazes de revelar erros relevantes. Compare o resultado com o pedido antes de concluir. Não afirme que executou testes ou observou resultados sem evidência. Informe limitações e pendências.
Para trabalhos extensos, registre progresso e estado necessário para retomar quando apropriado. Se faltar informação, prossiga com o que puder e indique as hipóteses que afetem o resultado.'''


def main():
    profile, alias = sys.argv[1:3]
    name = 'vk-local-' + profile
    key = open('/home/openhands/.openhands/agent-canvas/api-key.txt', encoding='utf-8').read().strip()
    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request('http://127.0.0.1:18000' + path, data=data,
                      headers={'X-Session-API-Key': key, 'Content-Type': 'application/json'})
        with urlopen(req, timeout=15) as response:
            return json.load(response)
    def get_or_none(path):
        try:
            return request(path)
        except HTTPError as e:
            if e.code == 404:
                return None
            raise
    suffix = quote(name, safe='')
    model_path = '/api/profiles/' + suffix
    model = get_or_none(model_path)
    if model is None:
        request(model_path, {'llm': {'model': 'openai/' + alias,
                                     'base_url': 'http://llama-server:8080/v1', 'api_key': 'local'}})
    else:
        cfg = model.get('config', {})
        if cfg.get('model') != 'openai/' + alias or cfg.get('base_url') != 'http://llama-server:8080/v1':
            raise ValueError('Perfil de modelo existente diverge; configuração preservada.')
    agent_path = '/api/agent-profiles/' + suffix
    agent = get_or_none(agent_path)
    if agent is None:
        request(agent_path, {'agent_kind': 'openhands', 'llm_profile_ref': name,
                             'system_message_suffix': INSTRUCOES})
        agent = request(agent_path)
    settings = agent['profile']
    if settings.get('agent_kind') != 'openhands' or settings.get('llm_profile_ref') != name:
        raise ValueError('Perfil de agente existente diverge; configuração preservada.')
    request('/api/agent-profiles/' + quote(settings['id'], safe='') + '/activate', {})
    print('Perfil ativo:', name)


if __name__ == '__main__':
    main()
