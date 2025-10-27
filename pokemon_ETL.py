import pandas as pd
import requests
import sys
import math
from pandas import json_normalize
from tqdm import tqdm 
import os
from dotenv import load_dotenv 


#configuração da API
load_dotenv()
url = os.getenv("API_URL")
username = os.getenv("API_USER")
password = os.getenv("API_PASS")

# Endpoints
login_endpoint = "/login"
endpoints = {
    "Listar Pokemons": "/pokemon",
    "Atributos de um Pokemon": "/pokemon/{pokemon_id}",
    "Listar Combates": "/combats"
}

#Nomes dos arquivos
OUTPUT_FILE_POKEMONS = "pokemons_lista.xlsx"
OUTPUT_FILE_ATRIBUTOS = "pokemons_atributos.xlsx"
OUTPUT_FILE_COMBATES = "combates_lista.xlsx"

#Funções
def pegar_token_jwt(username, password):
    #Autentica na API e retorna o token JWT
    login_url = f"{url}{login_endpoint}"
    payload = {"username": username, "password": password}
    
    try:
        response = requests.post(login_url, json=payload)
        response.raise_for_status() 
        token_data = response.json()
        return token_data.get("access_token")
    
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 401:
            print("\n[ERRO FATAL] Erro 401: Credenciais inválidas. Verifique seu usuário e senha.")
        else:
            print(f"\n[ERRO FATAL] Erro HTTP na autenticação: {http_err} - {response.text}")
    
    return None

def buscar_dados_simples(token, endpoint_url):
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(endpoint_url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            print(f"\n[AVISO 404] Recurso não encontrado em {endpoint_url}.")
        else:
            print(f"\n[ERRO HTTP] Erro ao buscar dados: {http_err} - {response.text}")
    return None

def buscar_dados_paginados(token, base_url, data_key):
    #busca todos os dados de um endpoint paginado
    print(f"Buscando dados paginados de '{base_url}' (chave: '{data_key}')...")
    all_data_list = []
    
    #busca a primeira página para descobrir o total
    response_dict = buscar_dados_simples(token, base_url)
    
    if not response_dict or data_key not in response_dict:
        print(f"[ERRO] Resposta de {base_url} não é um dict ou falta a chave esperada '{data_key}'.")
        return [] # Retorna lista vazia

    all_data_list.extend(response_dict.get(data_key, []))
    
    # 2. Pega os dados da paginação
    total_items = response_dict.get("total", 0)
    per_page = response_dict.get("per_page", 10)
    
    if total_items == 0 or per_page == 0:
        print("[AVISO] Dados de paginação 'total' ou 'per_page' não encontrados. Assumindo página única.")
        return all_data_list 

    total_pages = math.ceil(total_items / per_page)
    print(f"Total de {total_items} itens em {total_pages} páginas.")

    #loop para buscar as páginas restantes da 2 até a última
    if total_pages > 1:
        for page_num in tqdm(range(2, total_pages + 1), desc=f"Buscando '{data_key}'"):
            next_page_url = f"{base_url}?page={page_num}"
            response_dict = buscar_dados_simples(token, next_page_url)
            
            if response_dict and data_key in response_dict:
                all_data_list.extend(response_dict.get(data_key, []))
                
    print(f"Busca paginada concluída. Total de {len(all_data_list)} itens de '{data_key}'.")
    return all_data_list

#Processo de ETL

def main():
    token = pegar_token_jwt(username, password)
    
    if not token:
        sys.exit(1)

    #Buscar Lista de Pokémons 
    print("\n--- 1/3: Buscando lista de Pokémons ---")
    endpoint_lista = f"{url}{endpoints['Listar Pokemons']}"
    all_pokemons_list = buscar_dados_paginados(token, endpoint_lista, "pokemons")
    
    if not all_pokemons_list:
        print("Falha ao buscar a lista de Pokémons")
        sys.exit(1)
        
    df_pokemons = pd.DataFrame(all_pokemons_list)
    
    # Descobre a coluna de ID (id ou name)
    if 'id' in df_pokemons.columns:
        id_column_name = 'id'
    elif 'name' in df_pokemons.columns:
        id_column_name = 'name'
    else:
        print(f"Não encontrei 'id' ou 'name' na lista. Colunas: {list(df_pokemons.columns)}")
        sys.exit(1)
        
    identifier_list = df_pokemons[id_column_name].tolist()
    print(f"Usando coluna '{id_column_name}' como identificador para atributos.")
    
    #Buscar Atributos de CADA Pokémon 
    print("\n--- 2/3: Buscando atributos detalhados (isso pode demorar) ---")
    attributes_data = []
    endpoint_path_template = endpoints['Atributos de um Pokemon'] 

    for poke_id in tqdm(identifier_list, desc="Buscando Atributos"):
        url_detalhe = f"{url}{endpoint_path_template.replace('{pokemon_id}', str(poke_id))}"
        data_attr = buscar_dados_simples(token, url_detalhe)
        
        if data_attr:
            flat_data = json_normalize(data_attr)
            flat_data[f'source_{id_column_name}'] = poke_id
            attributes_data.append(flat_data)

    if not attributes_data:
        print("[AVISO] Nenhum dado de atributo foi encontrado.")
        df_atributos = pd.DataFrame()
    else:
        df_atributos = pd.concat(attributes_data, ignore_index=True)
    
    print(f"{len(df_atributos)} registros de atributos processados.")

    #Lista de Combates
    print("\n--- 3/3: Buscando lista de combates ---")
    endpoint_combates_url = f"{url}{endpoints['Listar Combates']}"
    all_combates_list = buscar_dados_paginados(token, endpoint_combates_url, "combats")
    
    if not all_combates_list:
        print("[AVISO] Nenhum dado de combate foi encontrado.")
        df_combates = pd.DataFrame()
    else:
        df_combates = pd.DataFrame(all_combates_list)
        
    print(f"{len(df_combates)} combates encontrados.")

    #Salvando dados no formato do Excel
    print(f"Salvando DataFrames em arquivos .xlsx separados")
    
    try:
        #Arquivo 1
        print(f"Salvando DataFrame de Pokémons em '{OUTPUT_FILE_POKEMONS}'...")
        df_pokemons.to_excel(OUTPUT_FILE_POKEMONS, index=False)
        
        #Arquivo 2
        print(f"Salvando DataFrame de Atributos em '{OUTPUT_FILE_ATRIBUTOS}'...")
        df_atributos.to_excel(OUTPUT_FILE_ATRIBUTOS, index=False)
        
        #Arquivo 3
        print(f"Salvando DataFrame de Combates em '{OUTPUT_FILE_COMBATES}'...")
        df_combates.to_excel(OUTPUT_FILE_COMBATES, index=False)
        
    except Exception as e:
        print(f"\n[ERRO FATAL] Falha ao salvar os arquivos Excel: {e}")
        print("Verifique se você tem permissão de escrita no diretório ou se algum arquivo está aberto.")


if __name__ == "__main__":
    main()