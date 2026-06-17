# Sistema de Inscrição Olimpíadas Universitárias

Sistema desenvolvido em Django com Tailwind CSS para gestão de inscrições em modalidades esportivas universitárias.

## Funcionalidades
- **Cadastro de Usuários:** Representantes (Atléticas/Servidores) podem criar suas contas.
- **Gestão de Atletas:** Cadastro prévio de atletas com todos os dados necessários (Matrícula, Curso, Campus).
- **Inscrições por Modalidade:** Montagem de equipes selecionando atletas cadastrados, respeitando limites mínimos e máximos.
- **Comprovação Digital:** Campo para link de documentos comprobatórios (Google Drive, etc).
- **Painel Administrativo:** Comissão pode gerenciar modalidades e encerrar inscrições.

## Como Executar Localmente

1. **Acesse a pasta do projeto:**
   ```bash
   cd olimpiadas_universitarias
   ```

2. **Ative o ambiente virtual:**
   ```bash
   source venv/bin/activate
   ```

3. **Inicie o servidor:**
   ```bash
   python manage.py runserver
   ```

4. **Acesse no navegador:** `http://127.0.0.1:8000`

## Credenciais de Admin
Para acessar o painel administrativo (`/admin`), você precisará criar um superusuário:
```bash
python manage.py createsuperuser
```

## Dicas para PythonAnywhere
1. Faça o upload da pasta `olimpiadas_universitarias`.
2. No Web Tab, configure o caminho do código e do VirtualEnv.
3. Configure o arquivo WSGI apontando para `olimpiadas_project.wsgi`.
4. Lembre-se de rodar `python manage.py collectstatic` no console do PythonAnywhere.
5. O sistema já usa o Tailwind Standalone, então não é necessário instalar Node.js no servidor.
