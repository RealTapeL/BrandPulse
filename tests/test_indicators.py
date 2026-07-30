"""指标计算纯函数单元测试（不依赖数据库）"""
import pytest

from brandpulse.indicators.heat import shop_heat
from brandpulse.indicators.momentum import momentum_and_volatility
from brandpulse.indicators.reputation import bayesian_weight


class TestBayesianWeight:
    def test_zero_votes_returns_prior(self):
        # 没有评价时，完全等于先验均值 C
        assert bayesian_weight(4.9, 0, c=4.0, m=10) == pytest.approx(4.0)

    def test_few_votes_pulled_toward_prior(self):
        # 少量高分评价会被拉向先验，不应接近满分
        w = bayesian_weight(5.0, 2, c=4.0, m=50)
        assert w < 4.2

    def test_many_votes_approach_raw_rating(self):
        # 大量评价时结果应贴近原始评分
        w = bayesian_weight(4.8, 10000, c=4.0, m=50)
        assert abs(w - 4.8) < 0.05

    def test_monotonic_in_votes(self):
        # 评分高于先验时，评价数越多加权分越高
        w1 = bayesian_weight(4.5, 10, c=4.0, m=20)
        w2 = bayesian_weight(4.5, 1000, c=4.0, m=20)
        assert w2 > w1


class TestShopHeat:
    def test_zero_reviews_is_zero(self):
        assert shop_heat(0) == 0.0

    def test_reference_point_is_100(self):
        # 5 万评价（基准值）应得到 100 分
        assert shop_heat(50000) == pytest.approx(100.0)

    def test_monotonic_and_sublinear(self):
        h1, h2, h3 = shop_heat(10), shop_heat(100), shop_heat(1000)
        assert 0 < h1 < h2 < h3
        # 对数压缩：评价数 10 倍增长，得分增长远小于 10 倍
        assert shop_heat(10000) / shop_heat(1000) < 2


class TestMomentum:
    def test_empty_series(self):
        wow, vol = momentum_and_volatility([])
        assert wow is None and vol is None

    def test_single_period_no_momentum(self):
        wow, vol = momentum_and_volatility([100.0])
        assert wow is None and vol is None

    def test_two_periods_growth(self):
        wow, vol = momentum_and_volatility([100.0, 110.0])
        assert wow == pytest.approx(0.10)
        assert vol is not None  # 满 2 期即可算波动率（窗口上限 4 期）

    def test_two_periods_decline(self):
        wow, _ = momentum_and_volatility([100.0, 90.0])
        assert wow == pytest.approx(-0.10)

    def test_previous_zero_returns_none(self):
        wow, _ = momentum_and_volatility([0.0, 50.0])
        assert wow is None

    def test_stable_series_low_volatility(self):
        wow, vol = momentum_and_volatility([100.0, 101.0, 99.0, 100.0])
        assert vol is not None
        assert vol < 0.05

    def test_volatile_series_high_volatility(self):
        _, vol = momentum_and_volatility([100.0, 200.0, 50.0, 300.0])
        assert vol is not None
        assert vol > 0.5
