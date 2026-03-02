"""
Concept Generator Tool

Генерация концептов по референсам через AIML API.

Usage:
    from studio.tools.concept_gen import generate_concepts

    results = generate_concepts(
        refs_dir="refs/",
        output_dir="output/",
        prompt="game UI concept"
    )
"""

from .generator import generate_concepts, analyze_reference, ConceptResult

__all__ = ["generate_concepts", "analyze_reference", "ConceptResult"]
