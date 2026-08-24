FROM ubuntu:20.04

LABEL maintainer="dongchaopeng@iie.ac.cn"

SHELL ["/bin/bash", "-c"]

RUN apt-get update && \
    apt-get install -y \
    wget \
    bzip2 \
    git \
    curl

RUN mkdir /root/miniconda3 && \
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh -O /root/miniconda3/miniconda.sh && \
    bash /root/miniconda3/miniconda.sh -b -u -p /root/miniconda3 && \
    rm -rf /root/miniconda3/miniconda.sh && \
    /root/miniconda3/bin/conda init bash

#RUN curl -LsSf https://hcli.docs.hex-rays.com/install | sh
#RUN /root/.local/bin/hcli --auth key login

#RUN /root/.local/bin/hcli ida install \
#    --set-default \
#    --accept-eula \
#    --yes \
#    --license-id $IDA_LICENSE_ID \
#    --download-id ida-classroom:latest

RUN mkdir -p /root/LibvDiff

COPY . /root/LibvDiff
WORKDIR /root/LibvDiff

RUN /root/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
RUN /root/miniconda3/bin/conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
RUN /root/miniconda3/bin/conda create -y --name libvdiff python=3.8
RUN /root/miniconda3/envs/libvdiff/bin/python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu129
RUN /root/miniconda3/envs/libvdiff/bin/python -m pip install -r requirements.txt




