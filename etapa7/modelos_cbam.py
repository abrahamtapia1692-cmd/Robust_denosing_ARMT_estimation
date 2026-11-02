#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Modelos neuronales CBAM y comparadores para magnetotelúrica (Etapa 7).

Contiene:
1. SCNet18_Classifier: Arquitectura exacta de Zhang et al. (2024) (identification/g12.py)
   para detección/clasificación multicanal (B3).
2. SCNet18_Denoiser: Arquitectura exacta de Zhang et al. (2024) (denoising/g15.py)
   para separación/denoising multicanal con proyección densa (B3).
3. CBAM_ResUNet_Denoiser: Separador adaptado (B4) que conserva los módulos de atención
   CBAM pero sustituye la proyección densa por un decodificador convolucional U-Net con
   equivarianza de escala y preservación de impedancia.
4. MultichannelWienerFilter: Cota analítica lineal óptima de Wiener (B8).
5. ChannelBalancedLoss: Función de pérdida física balanceada por canal para evitar el sesgo
   en la relación E/H = Z(f).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

VERSION = "P7-MOD-2.0.0"


# =============================================================================
# 1. Módulos canónicos de atención CBAM de Zhang et al. (2024)
# =============================================================================

class ChannelAttention(nn.Module):
    """Atención de canal CBAM exacta de Zhang et al. (2024) (g12.py / g15.py)."""

    def __init__(self, inchannel: int, ratio: int = 16):
        super(ChannelAttention, self).__init__()
        self.avg_pool = nn.AdaptiveAvgPool1d(1)
        self.max_pool = nn.AdaptiveMaxPool1d(1)

        reduced = max(2, inchannel // ratio)
        self.sharedMLP = nn.Sequential(
            nn.Conv1d(inchannel, reduced, 1, bias=False),
            nn.ReLU(inplace=True),
            nn.Conv1d(reduced, inchannel, 1, bias=False),
        )
        self.sigmoid = nn.Sigmoid()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        avgout = self.sharedMLP(self.avg_pool(x))
        maxout = self.sharedMLP(self.max_pool(x))
        return self.sigmoid(avgout + maxout)


class SpatialAttention(nn.Module):
    """Atención espacial/temporal CBAM exacta de Zhang et al. (2024) (g12.py / g15.py)."""

    def __init__(self, kernel_size: int = 7):
        super(SpatialAttention, self).__init__()
        assert kernel_size in (3, 7), "kernel size must be 3 or 7"
        padding = 3 if kernel_size == 7 else 1

        self.conv = nn.Conv1d(2, 1, kernel_size, padding=padding, bias=False)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        avgout = torch.mean(x, dim=1, keepdim=True)
        maxout, _ = torch.max(x, dim=1, keepdim=True)
        x_cat = torch.cat([avgout, maxout], dim=1)
        x_conv = self.conv(x_cat)
        return self.sigmoid(x_conv)


class BasicBlock(nn.Module):
    """Bloque residual ResNet con CBAM exacto de Zhang et al. (2024)."""
    expansion = 1

    def __init__(self, inchannel: int, outchannel: int, stride: int = 1):
        super(BasicBlock, self).__init__()
        self.left = nn.Sequential(
            nn.Conv1d(inchannel, outchannel, kernel_size=3, stride=stride, padding=1, bias=False),
            nn.BatchNorm1d(outchannel),
            nn.ReLU(inplace=True),
            nn.Conv1d(outchannel, outchannel, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm1d(outchannel),
        )
        self.ca = ChannelAttention(outchannel, ratio=16)
        self.sa = SpatialAttention(kernel_size=7)
        self.shortcut = nn.Sequential()
        if stride != 1 or inchannel != outchannel:
            self.shortcut = nn.Sequential(
                nn.Conv1d(inchannel, outchannel, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm1d(outchannel),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.left(x)
        out = self.ca(out) * out
        out = self.sa(out) * out
        out += self.shortcut(x)
        out = F.elu(out)
        return out


# =============================================================================
# 2. Arquitecturas B3: SCNet18 exactas de Zhang et al. (2024)
# =============================================================================

class SCNet18_Classifier(nn.Module):
    """Detector de ruido SCNet18 de Zhang et al. (2024) (identification/g12.py).

    Entrada: (B, 4, 256)
    Salida: Logits para 2 clases (0: limpio, 1: contaminado)
    """

    def __init__(self, in_channels: int = 4, num_classes: int = 2):
        super(SCNet18_Classifier, self).__init__()
        self.inchannel = 64
        self.conv1 = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm1d(64),
            nn.ELU(),
        )
        self.layer1 = self._make_layer(BasicBlock, 64, 2, stride=1)
        self.layer2 = self._make_layer(BasicBlock, 128, 2, stride=2)
        self.layer3 = self._make_layer(BasicBlock, 256, 2, stride=2)
        self.layer4 = self._make_layer(BasicBlock, 512, 2, stride=2)
        self.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(512 * 32, num_classes),
        )

    def _make_layer(self, block, channels: int, num_blocks: int, stride: int) -> nn.Sequential:
        strides = [stride] + [1] * (num_blocks - 1)
        layers = []
        for s in strides:
            layers.append(block(self.inchannel, channels, s))
            self.inchannel = channels
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, 4, 256)
        out = self.conv1(x)
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)
        out = F.avg_pool1d(out, kernel_size=3, stride=1, padding=1)
        out = out.view(out.size(0), -1)
        out = self.fc(out)
        return out

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            logits = self.forward(x)
            probs = F.softmax(logits, dim=-1)
            return probs[:, 1]  # Probabilidad de clase 1 (contaminado)


class SCNet18_Denoiser(nn.Module):
    """Separador de ruido SCNet18 de Zhang et al. (2024) (denoising/g15.py).

    Entrada: (B, 4, 256)
    Salida: Señal limpia estimada (B, 4, 256)
    """

    def __init__(self, in_channels: int = 4, out_channels: int = 4, data_size: int = 256):
        super(SCNet18_Denoiser, self).__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.data_size = data_size
        self.inchannel = 64
        self.conv1 = nn.Sequential(
            nn.Conv1d(in_channels, 64, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm1d(64),
            nn.ELU(),
        )
        self.layer1 = self._make_layer(BasicBlock, 64, 2, stride=1)
        self.layer2 = self._make_layer(BasicBlock, 128, 2, stride=2)
        self.layer3 = self._make_layer(BasicBlock, 256, 2, stride=2)
        self.layer4 = self._make_layer(BasicBlock, 512, 2, stride=2)
        self.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(512 * 32, out_channels * data_size),
        )

    def _make_layer(self, block, channels: int, num_blocks: int, stride: int) -> nn.Sequential:
        strides = [stride] + [1] * (num_blocks - 1)
        layers = []
        for s in strides:
            layers.append(block(self.inchannel, channels, s))
            self.inchannel = channels
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        # Normalización original de Zhang et al.: x / max(|x|) por ventana
        _range = torch.amax(torch.abs(x), dim=(1, 2), keepdim=True) + 1e-6
        x_norm = x / _range

        out = self.conv1(x_norm)
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)
        out = F.avg_pool1d(out, kernel_size=3, stride=1, padding=1)
        out = out.view(out.size(0), -1)
        out = self.fc(out)
        out = out.reshape((out.size(0), self.out_channels, self.data_size))

        s_hat = out * _range
        n_hat = x - s_hat
        return {"s_hat": s_hat, "n_hat": n_hat}


# =============================================================================
# 3. Arquitectura B4: CBAM Adaptado (Convolucional U-Net multiescala)
# =============================================================================

class CBAM_ResUNet_Denoiser(nn.Module):
    """Separador adaptado B4 con CBAM y decodificador convolucional multiescala.

    Corrige las limitaciones de SCNet18 (B3):
    1. Sustituye la capa densa de 16M parámetros por un decodificador convolucional
       que preserva la invarianza temporal por traslación.
    2. Equivarianza de escala estricta mediante RMS global por ventana.
    3. Conexiones residuales con inicialización cuasi-nula para identidad limpia exacta.
    """

    def __init__(self, in_channels: int = 4, base_channels: int = 32, reduction_ratio: int = 4):
        super().__init__()
        c = base_channels
        self.in_channels = in_channels

        # Codificador multiescala con CBAM
        self.enc1 = nn.Sequential(
            nn.Conv1d(in_channels, c, kernel_size=5, padding=2),
            nn.BatchNorm1d(c),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c, c, stride=1),
        )  # (B, 32, 256)

        self.down1 = nn.Sequential(
            nn.Conv1d(c, c * 2, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm1d(c * 2),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c * 2, c * 2, stride=1),
        )  # (B, 64, 128)

        self.down2 = nn.Sequential(
            nn.Conv1d(c * 2, c * 4, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm1d(c * 4),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c * 4, c * 4, stride=1),
        )  # (B, 128, 64)

        self.down3 = nn.Sequential(
            nn.Conv1d(c * 4, c * 8, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm1d(c * 8),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c * 8, c * 8, stride=1),
        )  # (B, 256, 32)

        # Cuello de botella
        self.bottleneck = nn.Sequential(
            nn.Conv1d(c * 8, c * 8, kernel_size=3, padding=1),
            nn.BatchNorm1d(c * 8),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c * 8, c * 8, stride=1),
        )  # (B, 256, 32)

        # Decodificador con convoluciones transpuestas y saltos
        self.up3 = nn.ConvTranspose1d(c * 8, c * 4, kernel_size=4, stride=2, padding=1)
        self.dec3 = nn.Sequential(
            nn.Conv1d(c * 8, c * 4, kernel_size=3, padding=1),
            nn.BatchNorm1d(c * 4),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c * 4, c * 4, stride=1),
        )

        self.up2 = nn.ConvTranspose1d(c * 4, c * 2, kernel_size=4, stride=2, padding=1)
        self.dec2 = nn.Sequential(
            nn.Conv1d(c * 4, c * 2, kernel_size=3, padding=1),
            nn.BatchNorm1d(c * 2),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c * 2, c * 2, stride=1),
        )

        self.up1 = nn.ConvTranspose1d(c * 2, c, kernel_size=4, stride=2, padding=1)
        self.dec1 = nn.Sequential(
            nn.Conv1d(c * 2, c, kernel_size=3, padding=1),
            nn.BatchNorm1d(c),
            nn.LeakyReLU(0.1, inplace=True),
            BasicBlock(c, c, stride=1),
        )

        # Proyección de ruido final
        self.out_conv = nn.Conv1d(c, in_channels, kernel_size=5, padding=2)
        nn.init.zeros_(self.out_conv.weight)
        nn.init.zeros_(self.out_conv.bias)

    def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        # x: (B, 4, 256)
        # Normalización RMS global (conserva exactamente la relación Ex/Hy y Ey/Hx)
        rms = torch.sqrt(torch.mean(x ** 2, dim=(1, 2), keepdim=True)) + 1e-6
        x_norm = x / rms

        e1 = self.enc1(x_norm)
        e2 = self.down1(e1)
        e3 = self.down2(e2)
        e4 = self.down3(e3)

        b = self.bottleneck(e4)

        d3 = self.dec3(torch.cat([self.up3(b), e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))

        n_norm = self.out_conv(d1)
        n_hat = n_norm * rms
        s_hat = x - n_hat
        return {"s_hat": s_hat, "n_hat": n_hat}


# =============================================================================
# 4. Función de pérdida física balanceada por canal (Plan v1.3 §7.5)
# =============================================================================

class ChannelBalancedLoss(nn.Module):
    """Pérdida multicanal normalizada por varianza fija de canal para preservar Z = E/H."""

    def __init__(
        self,
        lambda_time: float = 1.0,
        lambda_freq: float = 0.5,
        lambda_id: float = 1.0,
        channel_variances: Tuple[float, float, float, float] = (0.562, 0.568, 0.222, 0.221),
    ):
        super().__init__()
        self.lambda_time = lambda_time
        self.lambda_freq = lambda_freq
        self.lambda_id = lambda_id
        # Pesos inversos fijos por canal para balancear exactamente el aporte de Ex, Ey, Hx, Hy
        inv_vars = [1.0 / max(1e-4, v) for v in channel_variances]
        self.register_buffer("channel_weights", torch.tensor(inv_vars, dtype=torch.float32).view(1, 4, 1))
        self.huber = nn.SmoothL1Loss(reduction="none")

    def forward(
        self,
        s_hat: torch.Tensor,
        n_hat: torch.Tensor,
        s_true: torch.Tensor,
        is_clean_mask: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        # s_hat, s_true: (B, 4, 256)
        weights = self.channel_weights.to(s_hat.device)
        # 1. Pérdida temporal balanceada por canal (Ex, Ey, Hx, Hy ponderados equitativamente)
        raw_l_t = self.huber(s_hat, s_true)  # (B, 4, 256)
        l_time = torch.mean(raw_l_t * weights)

        # 2. Pérdida de espectro complejo por canal
        sh_f = torch.fft.rfft(s_hat, dim=-1)
        by_f = torch.fft.rfft(s_true, dim=-1)
        p_err_f = torch.mean(torch.abs(sh_f - by_f) ** 2, dim=-1, keepdim=True)  # (B, 4, 1)
        l_freq = torch.mean(p_err_f * weights)

        # 3. Identidad estricta en tramos limpios
        if torch.any(is_clean_mask):
            raw_l_id = self.huber(n_hat[is_clean_mask], torch.zeros_like(n_hat[is_clean_mask]))
            l_id = torch.mean(raw_l_id * weights)
        else:
            l_id = torch.tensor(0.0, device=s_hat.device)

        total_loss = self.lambda_time * l_time + self.lambda_freq * l_freq + self.lambda_id * l_id

        return {
            "total_loss": total_loss,
            "l_time": l_time.detach(),
            "l_freq": l_freq.detach(),
            "l_id": l_id.detach(),
        }


# =============================================================================
# 5. Cota analítica lineal óptima: Filtro de Wiener Multicanal (B8)
# =============================================================================

class MultichannelWienerFilter:
    """Filtro de Wiener multicanal (B8) para señales magnetotelúricas 4x4.

    Cota analítica lineal óptima para comparar el separador no lineal CBAM.
    Opera en el dominio espectral rfft para cada frecuencia k:
        W(k) = S_ss(k) [S_ss(k) + S_nn(k) + eps * I]^-1
        S_hat_wiener(k) = W(k) X(k)
    """

    def __init__(self, n_channels: int = 4, n_fft: int = 256, rcond: float = 1e-4):
        self.n_channels = n_channels
        self.n_fft = n_fft
        self.n_bins = n_fft // 2 + 1
        self.rcond = rcond
        self.s_ss = np.zeros((self.n_bins, n_channels, n_channels), dtype=complex)
        self.s_nn = np.zeros((self.n_bins, n_channels, n_channels), dtype=complex)
        self.wiener_matrices = np.zeros((self.n_bins, n_channels, n_channels), dtype=complex)
        # Ganancia escalar por bin: preserva Z(f) porque aplica el mismo factor
        # real a todos los canales (E y H) en cada frecuencia.
        self.scalar_gains = np.ones(self.n_bins, dtype=float)
        self.is_fitted = False
        self.mode = "multichannel_4x4"

    def fit(self, s_clean_windows: np.ndarray, n_noise_windows: np.ndarray) -> MultichannelWienerFilter:
        s_fft = np.fft.rfft(s_clean_windows, axis=1)  # (N, Bins, C)
        n_fft = np.fft.rfft(n_noise_windows, axis=1)  # (M, Bins, C)

        n_s = s_fft.shape[0]
        n_n = n_fft.shape[0]

        for k in range(self.n_bins):
            sk = s_fft[:, k, :]
            nk = n_fft[:, k, :]

            cov_ss = (sk.conj().T @ sk) / max(1, n_s)
            cov_nn = (nk.conj().T @ nk) / max(1, n_n)

            self.s_ss[k] = 0.5 * (cov_ss + cov_ss.conj().T)
            self.s_nn[k] = 0.5 * (cov_nn + cov_nn.conj().T)

            cov_xx = self.s_ss[k] + self.s_nn[k]
            reg = self.rcond * (np.trace(cov_xx).real / self.n_channels + 1e-12)
            cov_xx_reg = cov_xx + reg * np.eye(self.n_channels)

            try:
                inv_xx = np.linalg.pinv(cov_xx_reg)
                w_k = self.s_ss[k] @ inv_xx
            except np.linalg.LinAlgError:
                w_k = np.eye(self.n_channels, dtype=complex)

            self.wiener_matrices[k] = w_k

        self.is_fitted = True
        return self

    def filter_window(self, x_window: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("MultichannelWienerFilter must be fitted before filtering.")

        x_fft = np.fft.rfft(x_window, axis=0)
        s_hat_fft = np.zeros_like(x_fft)

        for k in range(self.n_bins):
            s_hat_fft[k] = self.wiener_matrices[k] @ x_fft[k]

        s_hat = np.fft.irfft(s_hat_fft, n=self.n_fft, axis=0)
        return s_hat

    def filter_batch(self, x_batch: np.ndarray) -> np.ndarray:
        b = x_batch.shape[0]
        out = np.zeros_like(x_batch)
        for i in range(b):
            out[i] = self.filter_window(x_batch[i])
        return out

    # ------------------------------------------------------------------
    # Variante Z-preserving (B8 riguroso)
    # ------------------------------------------------------------------
    # El filtro 4x4 completo mezcla canales E y H; al hacerlo puede alterar
    # Z(f)=E/H incluso sobre datos limpios, por lo que NO constituye una cota
    # lineal valida para MT. La variante escalar aplica una ganancia real
    # g(f) comun a los cuatro canales, de modo que Z(f) se conserva
    # exactamente (g(f) se cancela en el cociente E/H).
    def fit_scalar(self, s_clean_windows: np.ndarray, n_noise_windows: np.ndarray) -> "MultichannelWienerFilter":
        """Ajusta ganancias de Wiener escalares y reales por bin.

        g(f) = tr(S_ss(f)) / (tr(S_ss(f)) + tr(S_nn(f)))
        """
        s_fft = np.fft.rfft(s_clean_windows, axis=1)
        n_fft = np.fft.rfft(n_noise_windows, axis=1)

        n_s = max(1, s_fft.shape[0])
        n_n = max(1, n_fft.shape[0])

        for k in range(self.n_bins):
            sk = s_fft[:, k, :]
            nk = n_fft[:, k, :]
            cov_ss = (sk.conj().T @ sk) / n_s
            cov_nn = (nk.conj().T @ nk) / n_n
            p_ss = float(np.trace(cov_ss).real)
            p_nn = float(np.trace(cov_nn).real)
            self.scalar_gains[k] = p_ss / (p_ss + p_nn + 1e-12)

        self.mode = "scalar_z_preserving"
        self.is_fitted = True
        return self

    def filter_window_scalar(self, x_window: np.ndarray) -> np.ndarray:
        """Aplica la ganancia escalar por bin a una ventana (sin ventaneo)."""
        if not self.is_fitted:
            raise RuntimeError("MultichannelWienerFilter must be fitted before filtering.")
        x_fft = np.fft.rfft(x_window, axis=0)
        s_hat_fft = x_fft * self.scalar_gains[:, None]
        return np.fft.irfft(s_hat_fft, n=self.n_fft, axis=0)

    def filter_signal_wola(self, x_signal: np.ndarray, step: int = 128) -> np.ndarray:
        """Aplica la ganancia escalar con ventana Hann y overlap-add (WOLA).

        Para una ganancia comun a todos los canales, la relacion E/H se
        conserva exactamente; la ventana de analisis/sintesis evita
        discontinuidades de borde.
        """
        if not self.is_fitted:
            raise RuntimeError("MultichannelWienerFilter must be fitted before filtering.")
        x_signal = np.asarray(x_signal, dtype=float)
        n_samples = x_signal.shape[0]
        L = self.n_fft
        n = np.arange(L, dtype=float)
        hann = 0.5 - 0.5 * np.cos(2.0 * np.pi * (n + 0.5) / float(L))

        out = np.zeros_like(x_signal)
        weight = np.zeros(n_samples, dtype=float)

        for start in range(0, max(1, n_samples - L + 1), step):
            seg = x_signal[start : start + L] * hann[:, None]
            x_fft = np.fft.rfft(seg, axis=0)
            y = np.fft.irfft(x_fft * self.scalar_gains[:, None], n=L, axis=0)
            out[start : start + L] += y * hann[:, None]
            weight[start : start + L] += hann ** 2

        mask = weight > 1e-12
        out[mask] /= weight[mask, None]
        return out
