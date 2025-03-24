{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = [
    pkgs.python312
    pkgs.python312Packages.virtualenv
  ];
  shellHook = ''
    # Jika virtual environment belum ada, buat dengan nama .venv
    if [ ! -d ".venv" ]; then
      python3 -m venv .venv
      echo "Virtual environment .venv berhasil dibuat."
    fi

    # Aktifkan virtual environment
    source .venv/bin/activate

    # Upgrade pip dan install paket kurigram
    pip install --upgrade pip
    pip install kurigram python-dotenv

    echo "Environment siap. Virtual environment sudah aktif dan paket kurigram telah diinstall."
  '';
}
