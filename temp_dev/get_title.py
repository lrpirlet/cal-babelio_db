ttr=["Guerrier de Lumière - Volume 1"
    ,"Les juges : Trois histoires italiennes"
    ,"Dédicaces, Tome 2 : Le chapelet de jade et autres nouvelles"]

tmp_ttl=ttr[2]
bbl_series, bbl_series_seq ="", ""
tmp_ttl=tmp_ttl.replace("Tome","tome")
if ":" and "tome" in tmp_ttl:
    bbl_title=tmp_ttl.split(":")[-1].strip()
    print("bbl_title :",bbl_title)
    bbl_series=tmp_ttl.replace(" -", ",").split(":")[0].split(",")[0].strip()
    if bbl_series:
        bbl_series_seq = tmp_ttl.split("tome")[-1].split(":")[0].strip()
        if bbl_series_seq.isnumeric:
            bbl_series_seq = float(bbl_series_seq)
        else:
            bbl_series_seq = 0.0
else:
    bbl_title=tmp_ttl.strip()

print("bbl_title      : ", bbl_title)
if bbl_series:
    print("bbl_series     : ",bbl_series)
    print("bbl_series_seq : ",bbl_series_seq)
