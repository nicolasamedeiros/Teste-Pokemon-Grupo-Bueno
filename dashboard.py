import streamlit as st
import pandas as pd
import plotly.express as px
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
import os
import ast 

#configuração da página
st.set_page_config(layout="wide", page_title="Dashboard de Combates Pokémon")

#carregando dados
@st.cache_data
def load_data():
    try:
        data_folder = "dados"
        combates_file = os.path.join(data_folder, "combates_lista.xlsx")
        atributos_file = os.path.join(data_folder, "pokemons_atributos.xlsx")
        
        df_combates = pd.read_excel(combates_file)
        df_atributos = pd.read_excel(atributos_file)
        
        return df_combates, df_atributos

    except Exception as e:
        st.error(f"Ocorreu um erro ao ler os arquivos Excel. Erro: {e}")
        return None, None

#quais atributos mais influenciam a vitória ?
def analyze_feature_importance(df_combates, df_atributos):
    # Lista de colunas
    stat_cols = ['hp', 'attack', 'defense', 'sp_attack', 'sp_defense', 'speed']
    existing_stat_cols = [col for col in stat_cols if col in df_atributos.columns]
    
    id_col = 'id' 
    if id_col not in df_atributos.columns:
         st.error(f"Erro na Análise 1: A coluna '{id_col}' não foi encontrada no arquivo de atributos.")
         return None

    #juntar atributos aos combates
    df_merged = pd.merge(
        df_combates, 
        df_atributos, 
        left_on='first_pokemon', 
        right_on=id_col,
        suffixes=('', '_p1')
    )
    df_merged = pd.merge(
        df_merged, 
        df_atributos, 
        left_on='second_pokemon', 
        right_on=id_col,
        suffixes=('_p1', '_p2')
    )

    #criando diferenças
    features = []
    for stat in existing_stat_cols: 
        col_name_diff = f"{stat}_diff"
        df_merged[col_name_diff] = df_merged[f"{stat}_p1"] - df_merged[f"{stat}_p2"]
        features.append(col_name_diff)

    #criando alvo 
    df_merged['p1_wins'] = (df_merged['winner'] == df_merged['first_pokemon']).astype(int) 

    #treinando modelo
    X = df_merged[features]
    y = df_merged['p1_wins']
    
    if X.empty or y.empty:
        st.warning("Não foi possível gerar dados de treino para a análise de importância")
        return None

    X = X.fillna(0) 

    model = RandomForestClassifier(random_state=42)
    model.fit(X, y)

    #extraindo importância
    importance_df = pd.DataFrame({
        'Atributo (Diferença)': features,
        'Importância': model.feature_importances_
    }).sort_values(by='Importância', ascending=False)

    #gerar Gráfico
    fig = px.bar(
        importance_df,
        x='Importância',
        y='Atributo (Diferença)',
        orientation='h',
        title='Importância de Cada Atributo na Vitória'
    )
    fig.update_layout(yaxis={'categoryorder':'total ascending'})
    return fig

#qual a taxa de vitória por tipo ?
def analyze_type_winrate(df_combates, df_atributos):
    id_col = 'id' 
    type_col_name = 'types'
    
    if type_col_name not in df_atributos.columns:
        st.error(f"Erro na Análise 2: A coluna '{type_col_name}' não foi encontrada.")
        return None
    if id_col not in df_atributos.columns:
         st.error(f"Erro na Análise 2: A coluna '{id_col}' não foi encontrada.")
         return None

    #calcular vitórias e derrotas totais por pokemon
    wins = df_combates['winner'].value_counts()
    p1_fights = df_combates['first_pokemon'].value_counts()
    p2_fights = df_combates['second_pokemon'].value_counts()
    
    total_fights = p1_fights.add(p2_fights, fill_value=0)
    
    stats_pokemon = pd.DataFrame({
        'total_combates': total_fights,
        'total_vitorias': wins
    }).fillna(0)
    
    stats_pokemon['taxa_vitoria_pokemon'] = stats_pokemon['total_vitorias'] / stats_pokemon['total_combates']
    stats_pokemon = stats_pokemon.reset_index().rename(columns={'index': id_col})

    #seleciona as colunas de ID e tipos
    df_types_raw = df_atributos[[id_col, type_col_name]].copy()
    
    #essa função converte strings "['grass', 'poison']" em listas reais
    def safe_eval(type_str):
        try:
            return ast.literal_eval(str(type_str))
        except (ValueError, SyntaxError):
            return [str(type_str)]

    #aplica a função a lista em novas linhas
    df_types_long = df_types_raw.copy()
    df_types_long['type_list'] = df_types_raw[type_col_name].apply(safe_eval)
    df_types_long = df_types_long.explode('type_list')
    df_types_long = df_types_long.rename(columns={'type_list': 'type_name'})
    
    #juntar stats de vitória com os tipos explodidos
    df_merged_types = pd.merge(df_types_long, stats_pokemon, on=id_col)

    #calcular a média da taxa de vitória por tipo
    df_winrate_tipo = df_merged_types.groupby('type_name')['taxa_vitoria_pokemon'].mean().reset_index()
    df_winrate_tipo = df_winrate_tipo.sort_values(by='taxa_vitoria_pokemon', ascending=False)
    
    #gerar Gráfico
    fig = px.bar(
        df_winrate_tipo,
        x='type_name',
        y='taxa_vitoria_pokemon',
        title='Taxa de Vitória Média por Tipo de Pokémon',
        labels={'type_name': 'Tipo', 'taxa_vitoria_pokemon': 'Taxa de Vitória Média'}
    )
    fig.update_layout(xaxis={'categoryorder':'total descending'})
    return fig

#qual seria a composição da equipe dos sonhos ?
def analyze_dream_team(df_combates, df_atributos, min_combats):
    id_col = 'id' 
    type_col_name = 'types'
    
    if id_col not in df_atributos.columns:
         st.error(f"Erro na Análise 3: A coluna '{id_col}' não foi encontrada.")
         return pd.DataFrame() 

    #calcular vitórias e derrotas
    wins = df_combates['winner'].value_counts()
    p1_fights = df_combates['first_pokemon'].value_counts()
    p2_fights = df_combates['second_pokemon'].value_counts()
    total_fights = p1_fights.add(p2_fights, fill_value=0)
    
    stats_pokemon = pd.DataFrame({
        'total_combates': total_fights,
        'total_vitorias': wins
    }).fillna(0)
    
    stats_pokemon['taxa_vitoria_pokemon'] = stats_pokemon['total_vitorias'] / stats_pokemon['total_combates']
    stats_pokemon = stats_pokemon.reset_index().rename(columns={'index': id_col})
    
    #juntar com atributos para ter os tipos
    cols_to_merge = [id_col, 'name', type_col_name]
    
    cols_to_merge = [col for col in cols_to_merge if col in df_atributos.columns] 
    
    df_top_team = pd.merge(
        stats_pokemon,
        df_atributos[cols_to_merge],
        on=id_col,
        how='left'
    )
    
    df_top_team = df_top_team[df_top_team['total_combates'] >= min_combats]
    df_top_team = df_top_team.sort_values(by='taxa_vitoria_pokemon', ascending=False)
    
    #formatar para exibição
    df_top_team['taxa_vitoria_pokemon'] = (df_top_team['taxa_vitoria_pokemon'] * 100).round(2)
    cols_to_show = ['name', id_col, type_col_name, 'total_combates', 'total_vitorias', 'taxa_vitoria_pokemon']
    cols_to_show = [col for col in cols_to_show if col in df_top_team.columns]
    
    return df_top_team[cols_to_show]


#DASHBOARD

st.title("Análise Estratégica de Combates Pokemon (Kaisen)")

#carrega os dados
df_combates, df_atributos = load_data()

if df_combates is not None and df_atributos is not None:
    
    st.header("Pergunta 1: Quais atributos mais influenciam a vitória?")
    with st.spinner("Treinando modelo de Machine Learning..."):
        fig1 = analyze_feature_importance(df_combates, df_atributos)
        if fig1:
            st.plotly_chart(fig1, use_container_width=True)
            st.markdown("""
            O gráfico acima mostra a importância de cada atributo, calculada por um modelo de RandomForest.
            Um valor mais alto significa que a diferença nesse atributo entre os dois combatentes foi um fator mais decisivo para prever o vencedor.
            Atributos com barras maiores são os mais críticos para uma vitória.
            """)
        else:
            st.error("Não foi possível realizar a análise de importância dos atributos.")

    st.divider()

    st.header("Pergunta 2: Qual a taxa de vitória por tipo?")
    with st.spinner("Calculando taxas de vitória por tipo..."):
        fig2 = analyze_type_winrate(df_combates, df_atributos)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True)
            st.markdown("""
            Este gráfico mostra a taxa de vitória *média* de todos os Pokémon de um determinado tipo. 
            """)
        else:
            st.error("Não foi possível realizar a análise de tipos.")

    st.divider()

    st.header("Pergunta 3: Qual seria a composição da equipe dos sonhos?")
    
    # Filtro na Sidebar
    min_combats = st.sidebar.slider(
        "Mínimo de combates (Pergunta 3):",
        min_value=1,
        max_value=50,
        value=20, 
        help="Use este filtro para incluir na 'Equipe dos Sonhos' apenas Pokémon que lutaram um número mínimo de vezes"
    )
    
    st.info(f"Mostrando Pokémon com **{min_combats}** ou mais combates.")
    
    with st.spinner("Rankeando os melhores combatentes..."):
        df_team = analyze_dream_team(df_combates, df_atributos, min_combats)
        if not df_team.empty:
            st.dataframe(df_team.head(20), use_container_width=True)
            st.markdown("""
            A tabela acima mostra os Pokémon com a maior taxa de vitória individual, filtrados pelo mínimo de combates selecionado.
            Uma equipe dos sonhos ideal não conteria apenas os mais fortes, mas também uma boa cobertura de tipos
            """)
        else:
            st.warning("Nenhum Pokemon encontrado com os critérios de filtro selecionados.")

else:
    st.info("Aguardando o carregamento dos dados... Se o erro persistir, verifique os nomes dos arquivos e a subpasta.")