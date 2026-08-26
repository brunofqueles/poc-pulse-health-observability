"""
AgenteAutomacaoGit — automação de branch/commit/PR via API REST do GitHub.

Nível A (decisão consciente, ADR pendente): o agente cria branch, commita
1 arquivo por vez e abre o PR — merge continua sempre manual, revisado por
uma pessoa. Nenhum método de merge é implementado propositalmente.

MVP: 1 arquivo por commit, via "Create or update file contents"
(PUT /repos/{owner}/{repo}/contents/{path}) — confirmado contra a
documentação oficial do GitHub antes de implementar. Múltiplos arquivos
por commit (Git Database API: Blobs -> Tree -> Commit -> Ref, ou GraphQL
createCommitOnBranch) fica como evolução futura, não implementada agora —
a superfície de implementação do caso multi-arquivo é bem maior, e não há
necessidade real comprovada ainda.

Credencial (Personal Access Token, escopo `repo`) via Databricks Secret
Scope (pulse-secrets/github-pat), nunca em texto no código — mesmo padrão
já usado para a senha de aplicativo do Gmail.
"""

import base64
import requests


class AgenteAutomacaoGit:
    """Automação de Git via API REST do GitHub — branch, commit de 1 arquivo, e abertura de PR."""

    def __init__(self, dbutils, owner: str, repo: str, branch_base: str = "main"):
        token = dbutils.secrets.get(scope="pulse-secrets", key="github-pat")
        self.owner = owner
        self.repo = repo
        self.branch_base = branch_base
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
        self.base_url = f"https://api.github.com/repos/{owner}/{repo}"

    def criar_branch(self, nome_branch: str) -> dict:
        """Cria uma branch nova a partir do SHA atual de branch_base."""
        resp_base = requests.get(f"{self.base_url}/git/ref/heads/{self.branch_base}", headers=self.headers)
        if resp_base.status_code != 200:
            return {"sucesso": False, "status_code": resp_base.status_code, "erro": resp_base.text}

        sha_base = resp_base.json()["object"]["sha"]

        resp_criar = requests.post(
            f"{self.base_url}/git/refs",
            headers=self.headers,
            json={"ref": f"refs/heads/{nome_branch}", "sha": sha_base},
        )
        return {
            "sucesso": resp_criar.status_code == 201,
            "status_code": resp_criar.status_code,
            "branch": nome_branch,
        }

    def commitar_arquivo(self, branch: str, caminho_arquivo: str, conteudo: str, mensagem: str) -> dict:
        """
        Cria ou atualiza 1 arquivo na branch informada, via Contents API.
        Busca o SHA atual automaticamente se o arquivo já existir (obrigatório
        para atualização; ausente para criação de arquivo novo).
        """
        conteudo_b64 = base64.b64encode(conteudo.encode("utf-8")).decode("utf-8")

        resp_get = requests.get(
            f"{self.base_url}/contents/{caminho_arquivo}",
            headers=self.headers,
            params={"ref": branch},
        )
        sha_existente = resp_get.json().get("sha") if resp_get.status_code == 200 else None

        payload = {"message": mensagem, "content": conteudo_b64, "branch": branch}
        if sha_existente:
            payload["sha"] = sha_existente

        resp_put = requests.put(f"{self.base_url}/contents/{caminho_arquivo}", headers=self.headers, json=payload)
        sucesso = resp_put.status_code in (200, 201)

        return {
            "sucesso": sucesso,
            "status_code": resp_put.status_code,
            "commit_sha": resp_put.json().get("commit", {}).get("sha") if sucesso else None,
            "criado_ou_atualizado": "atualizado" if sha_existente else "criado",
        }

    def abrir_pr(self, branch: str, titulo: str, descricao: str) -> dict:
        """Abre o Pull Request de branch para branch_base. Nunca faz merge (Nível A)."""
        resp = requests.post(
            f"{self.base_url}/pulls",
            headers=self.headers,
            json={"title": titulo, "body": descricao, "head": branch, "base": self.branch_base},
        )
        sucesso = resp.status_code == 201
        return {
            "sucesso": sucesso,
            "status_code": resp.status_code,
            "url": resp.json().get("html_url") if sucesso else resp.text,
        }

    def publicar_mudanca(
        self,
        nome_branch: str,
        caminho_arquivo: str,
        conteudo: str,
        mensagem_commit: str,
        titulo_pr: str,
        descricao_pr: str,
    ) -> dict:
        """
        Ponto de entrada único: orquestra os 3 passos do Nível A em
        sequência (criar branch -> commitar 1 arquivo -> abrir PR). Para
        cedo se qualquer etapa falhar, sem tentar as seguintes sobre um
        estado inconsistente (ex.: commitar numa branch que não existe).

        Nunca faz merge — quem revisa e mescla é sempre uma pessoa.
        """
        resultado_branch = self.criar_branch(nome_branch)
        if not resultado_branch["sucesso"]:
            return {"sucesso": False, "etapa_falhou": "criar_branch", "detalhes": resultado_branch}

        resultado_commit = self.commitar_arquivo(nome_branch, caminho_arquivo, conteudo, mensagem_commit)
        if not resultado_commit["sucesso"]:
            return {"sucesso": False, "etapa_falhou": "commitar_arquivo", "detalhes": resultado_commit}

        resultado_pr = self.abrir_pr(nome_branch, titulo_pr, descricao_pr)
        if not resultado_pr["sucesso"]:
            return {"sucesso": False, "etapa_falhou": "abrir_pr", "detalhes": resultado_pr}

        return {
            "sucesso": True,
            "branch": nome_branch,
            "commit_sha": resultado_commit["commit_sha"],
            "pr_url": resultado_pr["url"],
        }