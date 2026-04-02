from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field


@dataclass
class Prior:
    mean: float
    variance: float

    @property
    def std(self) -> float:
        return math.sqrt(max(self.variance, 1e-9))

    def update(self, likelihood_mean: float, likelihood_var: float, n_obs: int) -> "Prior":
        if n_obs <= 0:
            return self
        prec_prior = 1.0 / max(self.variance, 1e-9)
        prec_like = n_obs / max(likelihood_var, 1e-9)
        post_mean = (prec_prior * self.mean + prec_like * likelihood_mean) / (prec_prior + prec_like)
        post_var = 1.0 / (prec_prior + prec_like)
        return Prior(post_mean, post_var)


@dataclass
class TeamParams:
    team: str
    division: str
    country: str
    attack_prior: Prior = field(default_factory=lambda: Prior(0.0, 0.3))
    defence_prior: Prior = field(default_factory=lambda: Prior(0.0, 0.3))
    n_matches: int = 0


@dataclass
class HierarchyLevel:
    name: str
    attack_hyperprior: Prior = field(default_factory=lambda: Prior(0.0, 0.5))
    defence_hyperprior: Prior = field(default_factory=lambda: Prior(0.0, 0.5))


class HierarchicalBayesianModel:
    GLOBAL_MEAN_GOALS = 1.35

    def __init__(self, home_advantage: float = 0.20, min_matches_full_trust: int = 30, use_xg_as_observation: bool = True):
        self.global_attack = Prior(0.0, 0.5)
        self.global_defence = Prior(0.0, 0.5)
        self.home_advantage = home_advantage
        self.min_matches = min_matches_full_trust
        self.use_xg = use_xg_as_observation
        self.countries: dict[str, HierarchyLevel] = {}
        self.divisions: dict[str, HierarchyLevel] = {}
        self.teams: dict[str, TeamParams] = {}

    def _ensure_country(self, country: str) -> HierarchyLevel:
        if country not in self.countries:
            self.countries[country] = HierarchyLevel(
                name=country,
                attack_hyperprior=Prior(self.global_attack.mean, self.global_attack.variance),
                defence_hyperprior=Prior(self.global_defence.mean, self.global_defence.variance),
            )
        return self.countries[country]

    def _ensure_division(self, division: str, country: str) -> HierarchyLevel:
        key = f"{country}::{division}"
        if key not in self.divisions:
            country_level = self._ensure_country(country)
            self.divisions[key] = HierarchyLevel(
                name=key,
                attack_hyperprior=Prior(country_level.attack_hyperprior.mean, country_level.attack_hyperprior.variance * 1.5),
                defence_hyperprior=Prior(country_level.defence_hyperprior.mean, country_level.defence_hyperprior.variance * 1.5),
            )
        return self.divisions[key]

    def _ensure_team(self, team: str, division: str, country: str) -> TeamParams:
        if team not in self.teams:
            div = self._ensure_division(division, country)
            self.teams[team] = TeamParams(
                team=team,
                division=division,
                country=country,
                attack_prior=Prior(div.attack_hyperprior.mean, div.attack_hyperprior.variance),
                defence_prior=Prior(div.defence_hyperprior.mean, div.defence_hyperprior.variance),
            )
        return self.teams[team]

    def update(
        self,
        home_team: str,
        away_team: str,
        home_goals: int,
        away_goals: int,
        home_xg: float,
        away_xg: float,
        division: str,
        country: str,
    ) -> None:
        obs_home = home_xg if self.use_xg else float(home_goals)
        obs_away = away_xg if self.use_xg else float(away_goals)
        home = self._ensure_team(home_team, division, country)
        away = self._ensure_team(away_team, division, country)

        mu = math.log(self.GLOBAL_MEAN_GOALS)
        log_obs_home = math.log(max(obs_home, 0.05))
        log_obs_away = math.log(max(obs_away, 0.05))

        residual_home_attack = log_obs_home - mu - away.defence_prior.mean - self.home_advantage
        residual_away_attack = log_obs_away - mu - home.defence_prior.mean

        obs_var = 0.20
        home.attack_prior = home.attack_prior.update(residual_home_attack, obs_var, 1)
        away.attack_prior = away.attack_prior.update(residual_away_attack, obs_var, 1)

        residual_away_def = log_obs_home - home.attack_prior.mean - mu - self.home_advantage
        residual_home_def = log_obs_away - away.attack_prior.mean - mu
        away.defence_prior = away.defence_prior.update(residual_away_def, obs_var, 1)
        home.defence_prior = home.defence_prior.update(residual_home_def, obs_var, 1)

        home.n_matches += 1
        away.n_matches += 1
        self._update_division_hyperpriors(division, country)

    def _update_division_hyperpriors(self, division: str, country: str) -> None:
        key = f"{country}::{division}"
        div_teams = [t for t in self.teams.values() if t.division == division and t.country == country]
        if len(div_teams) < 2:
            return
        attack_means = [t.attack_prior.mean for t in div_teams]
        defence_means = [t.defence_prior.mean for t in div_teams]
        self.divisions[key].attack_hyperprior = Prior(statistics.mean(attack_means), statistics.variance(attack_means) if len(attack_means) > 1 else 0.3)
        self.divisions[key].defence_hyperprior = Prior(statistics.mean(defence_means), statistics.variance(defence_means) if len(defence_means) > 1 else 0.3)

    def predict_lambdas(self, home_team: str, away_team: str, division: str, country: str) -> dict:
        home = self._ensure_team(home_team, division, country)
        away = self._ensure_team(away_team, division, country)
        mu = math.log(self.GLOBAL_MEAN_GOALS)

        log_lam_home = mu + home.attack_prior.mean + away.defence_prior.mean + self.home_advantage
        log_lam_away = mu + away.attack_prior.mean + home.defence_prior.mean
        lam_home = math.exp(log_lam_home)
        lam_away = math.exp(log_lam_away)

        var_log_home = home.attack_prior.variance + away.defence_prior.variance
        var_log_away = away.attack_prior.variance + home.defence_prior.variance
        std_home = lam_home * math.sqrt(max(var_log_home, 1e-9))
        std_away = lam_away * math.sqrt(max(var_log_away, 1e-9))

        shrink_home = min(1.0, home.n_matches / max(self.min_matches, 1))
        shrink_away = min(1.0, away.n_matches / max(self.min_matches, 1))

        return {
            "lambda_home": round(lam_home, 4),
            "lambda_away": round(lam_away, 4),
            "std_home": round(std_home, 4),
            "std_away": round(std_away, 4),
            "ci_home_95": (round(max(0.0, lam_home - 1.96 * std_home), 4), round(lam_home + 1.96 * std_home, 4)),
            "ci_away_95": (round(max(0.0, lam_away - 1.96 * std_away), 4), round(lam_away + 1.96 * std_away, 4)),
            "shrinkage_home": round(shrink_home, 3),
            "shrinkage_away": round(shrink_away, 3),
            "note": "HIGH_UNCERTAINTY" if shrink_home < 0.3 or shrink_away < 0.3 else "RELIABLE",
        }

    def to_dict(self) -> dict:
        return {
            "global_attack": {"mean": self.global_attack.mean, "variance": self.global_attack.variance},
            "global_defence": {"mean": self.global_defence.mean, "variance": self.global_defence.variance},
            "home_advantage": self.home_advantage,
            "min_matches": self.min_matches,
            "use_xg": self.use_xg,
            "countries": {
                k: {
                    "name": v.name,
                    "attack": {"mean": v.attack_hyperprior.mean, "variance": v.attack_hyperprior.variance},
                    "defence": {"mean": v.defence_hyperprior.mean, "variance": v.defence_hyperprior.variance},
                }
                for k, v in self.countries.items()
            },
            "divisions": {
                k: {
                    "name": v.name,
                    "attack": {"mean": v.attack_hyperprior.mean, "variance": v.attack_hyperprior.variance},
                    "defence": {"mean": v.defence_hyperprior.mean, "variance": v.defence_hyperprior.variance},
                }
                for k, v in self.divisions.items()
            },
            "teams": {
                k: {
                    "team": v.team,
                    "division": v.division,
                    "country": v.country,
                    "attack": {"mean": v.attack_prior.mean, "variance": v.attack_prior.variance},
                    "defence": {"mean": v.defence_prior.mean, "variance": v.defence_prior.variance},
                    "n_matches": v.n_matches,
                }
                for k, v in self.teams.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "HierarchicalBayesianModel":
        model = cls(
            home_advantage=float(payload.get("home_advantage", 0.20)),
            min_matches_full_trust=int(payload.get("min_matches", 30)),
            use_xg_as_observation=bool(payload.get("use_xg", True)),
        )
        raw_ga = payload.get("global_attack", {})
        raw_gd = payload.get("global_defence", {})
        model.global_attack = Prior(float(raw_ga.get("mean", 0.0)), float(raw_ga.get("variance", 0.5)))
        model.global_defence = Prior(float(raw_gd.get("mean", 0.0)), float(raw_gd.get("variance", 0.5)))

        for k, v in (payload.get("countries") or {}).items():
            model.countries[k] = HierarchyLevel(
                name=str(v.get("name", k)),
                attack_hyperprior=Prior(float(v.get("attack", {}).get("mean", 0.0)), float(v.get("attack", {}).get("variance", 0.5))),
                defence_hyperprior=Prior(float(v.get("defence", {}).get("mean", 0.0)), float(v.get("defence", {}).get("variance", 0.5))),
            )

        for k, v in (payload.get("divisions") or {}).items():
            model.divisions[k] = HierarchyLevel(
                name=str(v.get("name", k)),
                attack_hyperprior=Prior(float(v.get("attack", {}).get("mean", 0.0)), float(v.get("attack", {}).get("variance", 0.5))),
                defence_hyperprior=Prior(float(v.get("defence", {}).get("mean", 0.0)), float(v.get("defence", {}).get("variance", 0.5))),
            )

        for k, v in (payload.get("teams") or {}).items():
            model.teams[k] = TeamParams(
                team=str(v.get("team", k)),
                division=str(v.get("division", "")),
                country=str(v.get("country", "")),
                attack_prior=Prior(float(v.get("attack", {}).get("mean", 0.0)), float(v.get("attack", {}).get("variance", 0.3))),
                defence_prior=Prior(float(v.get("defence", {}).get("mean", 0.0)), float(v.get("defence", {}).get("variance", 0.3))),
                n_matches=int(v.get("n_matches", 0)),
            )
        return model

    def save(self, file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False)

    @classmethod
    def load(cls, file_path: str) -> "HierarchicalBayesianModel":
        with open(file_path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
        return cls.from_dict(payload)
