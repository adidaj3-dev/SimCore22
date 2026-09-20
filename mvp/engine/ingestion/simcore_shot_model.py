class SimCore22Shot:
    """
    Minimal placeholder shot model used by GSPro ingestion.
    This can be expanded later if needed.
    """

    def __init__(self, hole, par, score, fir, gir, putts, penalties):
        self.hole = hole
        self.par = par
        self.score = score
        self.fir = fir
        self.gir = gir
        self.putts = putts
        self.penalties = penalties

    def to_dict(self):
        return {
            "hole": self.hole,
            "par": self.par,
            "score": self.score,
            "fir": self.fir,
            "gir": self.gir,
            "putts": self.putts,
            "penalties": self.penalties,
        }