"""
Utilities for extracting database schema information and generating
join-related chunks for a Retrieval Augmented Generation (RAG) system
used in Text-to-SQL pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy import create_engine, MetaData
from sqlalchemy.engine import Engine
import networkx as nx


def extract_schema(connection_string: str, tables: Optional[List[str]] = None) -> MetaData:
    """
    Reflect the database schema using SQLAlchemy.
    
    Args:
        connection_string: SQLAlchemy database URI
        tables: Specific table names to reflect (None = all tables)
    
    Returns:
        A MetaData instance populated with tables and constraints
    """
    engine: Engine = create_engine(connection_string)
    metadata = MetaData()
    
    if tables:
        # Sadece belirtilen tabloları yansıt
        for table_name in tables:
            metadata.reflect(bind=engine, only=[table_name])
    else:
        # Tüm tabloları yansıt
        metadata.reflect(bind=engine)
    
    return metadata


def build_schema_graph(metadata: MetaData) -> nx.Graph:
    """
    Build an undirected schema graph from SQLAlchemy metadata.
    
    Each table is a node, foreign keys create edges.
    
    Args:
        metadata: SQLAlchemy MetaData object with reflected tables
    
    Returns:
        NetworkX Graph with join conditions
    """
    graph = nx.Graph()
    
    # Add nodes for each table
    for table_name in metadata.tables:
        graph.add_node(table_name)
    
    # Add edges for foreign key relationships
    for table in metadata.tables.values():
        for fk in table.foreign_keys:
            child_table = fk.parent.table.name
            parent_table = fk.column.table.name
            
            # Build join condition
            condition = f"{child_table}.{fk.parent.name} = {parent_table}.{fk.column.name}"
            
            # Add edge with condition
            graph.add_edge(child_table, parent_table, condition=condition)
    
    return graph


def find_join_paths(graph: nx.Graph, source: str, target: str) -> List[List[str]]:
    """
    Find all shortest join paths between two tables.
    
    Args:
        graph: Schema graph
        source: Starting table
        target: Ending table
    
    Returns:
        List of paths (each path is a list of table names)
    """
    try:
        return list(nx.all_shortest_paths(graph, source, target))
    except nx.NetworkXNoPath:
        return []


def generate_join_statement(graph: nx.Graph, path: List[str]) -> str:
    """
    Construct a SQL JOIN clause from a path of tables.
    
    Args:
        graph: Schema graph
        path: List of table names representing a join path
    
    Returns:
        SQL JOIN string
    """
    joins: List[str] = []
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        condition = graph[a][b]['condition']
        joins.append(f"JOIN {b} ON {condition}")
    return " ".join(joins)


def generate_join_chunks(graph: nx.Graph, main_table: Optional[str] = None) -> List[Dict[str, object]]:
    """
    Enumerate join paths and create descriptive chunks.
    
    Args:
        graph: Schema graph
        main_table: Optional main table to prioritize in descriptions
    
    Returns:
        List of dicts with 'path', 'description', and 'type' keys
    """
    chunks: List[Dict[str, object]] = []
    tables = sorted(graph.nodes)
    
    for idx, src in enumerate(tables):
        for dst in tables[idx + 1:]:
            paths = find_join_paths(graph, src, dst)
            
            for path in paths:
                join_stmt = generate_join_statement(graph, path)
                
                # Main table'ı vurgula
                if main_table and main_table in path:
                    desc_type = "primary_join"
                    description = f"🔵 PRIMARY JOIN: {src} to {dst} via main table {main_table}: {join_stmt}"
                else:
                    desc_type = "secondary_join"
                    description = f"Join path for {src} to {dst}: {join_stmt}"
                
                chunks.append({
                    "path": path,
                    "description": description,
                    "type": desc_type,
                    "source_table": src,
                    "target_table": dst
                })
    
    return chunks


def table_descriptions(metadata: MetaData, main_table: Optional[str] = None) -> List[Dict[str, object]]:
    """
    Generate textual descriptions for each table.
    
    Args:
        metadata: SQLAlchemy metadata
        main_table: Optional main table to mark as primary
    
    Returns:
        List of dicts with table info
    """
    docs: List[Dict[str, object]] = []
    
    for table in metadata.tables.values():
        columns_info = [f"{col.name} ({col.type})" for col in table.columns]
        cols_str = ", ".join(columns_info)
        
        is_main = table.name == main_table
        
        if is_main:
            description = f"⭐ MAIN TABLE: {table.name} (denormalized, use this first) - Columns: {cols_str}"
            doc_type = "main_table"
        else:
            description = f"Table {table.name} has columns: {cols_str}"
            doc_type = "table"
        
        docs.append({
            "table_name": table.name,
            "description": description,
            "type": doc_type,
            "columns": [col.name for col in table.columns]
        })
    
    return docs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate table and join chunks")
    parser.add_argument("connection", help="SQLAlchemy connection string")
    parser.add_argument("--tables", nargs="+", help="Specific tables to include")
    args = parser.parse_args()
    
    md = extract_schema(args.connection, args.tables)
    g = build_schema_graph(md)
    
    print("-- Table descriptions --")
    for desc in table_descriptions(md):
        print(desc['description'])
    
    print("\n-- Join chunks --")
    for chunk in generate_join_chunks(g):
        print(chunk['description'])