"""
Tests unitaires pour la couche d'accélération matérielle extrême (RTX 5090, RTX Pro, Apple M5 Ultra).
Valide la détection de profils, les stratégies de rendu Path Tracing et les pipelines d'encodage vidéo AV1/ProRes.
"""

import pytest
import numpy as np

from src.render.hardware_acceleration import (
    GPUArchitecture, HardwareProfile, HardwareAcceleratorManager, HardwareAcceleratedNeuralSDF
)
from src.core.geometry import make_box


def test_hardware_profile_detection() -> None:
    """Vérifie la détection du profil matériel hôte sans plantage."""
    profile = HardwareAcceleratorManager.detect_hardware()
    assert profile is not None
    assert profile.device_name != ""
    assert profile.total_memory_gb > 0.0
    assert len(profile.supported_video_codecs) > 0


def test_rtx5090_hardware_strategy() -> None:
    """Vérifie la stratégie de rendu et d'encodage dédiée à la NVIDIA RTX 5090."""
    profile_5090 = HardwareProfile(
        architecture=GPUArchitecture.NVIDIA_BLACKWELL_RTX5090,
        device_name="NVIDIA GeForce RTX 5090",
        total_memory_gb=32.0,
        is_unified_memory=False,
        has_hardware_raytracing=True,
        has_tensor_cores=True,
        has_hardware_video_encoding=True,
        supported_video_codecs=("Dual NVENC AV1 8K", "HEVC 4K240"),
        max_recommended_assembly_parts=200000,
        max_recommended_fem_nodes=5000000
    )

    render_strat = HardwareAcceleratorManager.get_render_pipeline_strategy(profile_5090)
    assert "OptiX" in render_strat["backend"] or "Vulkan" in render_strat["backend"]
    assert "2.5 milliards de rayons/s" in render_strat["ray_budget_per_sec"]

    video_strat = HardwareAcceleratorManager.get_video_encoding_strategy(profile_5090)
    assert video_strat["hardware_acceleration_active"] is True
    assert "AV1" in str(video_strat["supported_codec"])
    assert "8K" in str(video_strat["max_resolution"])


def test_apple_m5_ultra_hardware_strategy() -> None:
    """Vérifie la stratégie de rendu et de streaming spatial pour l'Apple M5 Ultra."""
    profile_m5 = HardwareProfile(
        architecture=GPUArchitecture.APPLE_SILICON_M_ULTRA,
        device_name="Apple M5 Ultra (120 GPU Cores)",
        total_memory_gb=192.0,
        is_unified_memory=True,
        has_hardware_raytracing=True,
        has_tensor_cores=True,
        has_hardware_video_encoding=True,
        supported_video_codecs=("Apple ProRes 422 HQ", "AV1 8K", "Spatial Video"),
        max_recommended_assembly_parts=500000,
        max_recommended_fem_nodes=2000000
    )

    render_strat = HardwareAcceleratorManager.get_render_pipeline_strategy(profile_m5)
    assert "Metal 4" in render_strat["backend"]
    assert "Dynamic Caching" in render_strat["features"]

    video_strat = HardwareAcceleratorManager.get_video_encoding_strategy(profile_m5)
    assert video_strat["hardware_acceleration_active"] is True
    assert "ProRes" in str(video_strat["supported_codec"])
    assert "Vision Pro" in str(video_strat["remote_streaming_protocol"])


def test_batch_accelerated_neural_sdf() -> None:
    """Vérifie le calcul par paquets d'un volume de distance signée sur 5000 points."""
    box = make_box(20.0, 20.0, 20.0)
    mesh = box.manifold.to_mesh()
    verts = np.array(mesh.vert_properties)[:, :3]
    faces = np.array(mesh.tri_verts)

    # 5000 points aléatoires dans [-30, 30]
    np.random.seed(42)
    query_pts = np.random.uniform(-30.0, 30.0, size=(5000, 3))

    profile = HardwareAcceleratorManager.detect_hardware()
    dists = HardwareAcceleratedNeuralSDF.compute_batch_sdf(verts, faces, query_pts, profile)

    assert dists.shape == (5000,)
    # Il doit y avoir à la fois des points intérieurs (<0) et extérieurs (>0)
    assert np.any(dists < 0.0)
    assert np.any(dists > 0.0)
