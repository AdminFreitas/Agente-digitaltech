---
title: "Implementar Evidência de Chaves Públicas no Kubernetes"
slug: "como-implementar-evidencia-de-chaves-publicas-no-kubernetes-para-melhorar-segura"
category: "Open Source"
description: "Fortaleça a segurança de seus workloads no Kubernetes com prova de posse de chaves públicas. Descubra como implementar agora."
date: "2026-08-07 01:52:16.632333+00:00"
readTime: "3 min"
tags: []
image: "https://images.unsplash.com/photo-1667372459607-2cfe842fdc4b?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&ixid=M3wxMDA2NDQwfDB8MXxzZWFyY2h8NXx8SW1wbGVtZW50YXIlMjBFdmlkJUMzJUFBbmNpYSUyMENoYXZlcyUyMFAlQzMlQkFibGljYXMlMjBLdWJlcm5ldGVzfGVufDB8MHx8fDE3ODYwNjcxMzR8MA&ixlib=rb-4.1.0&q=80&w=400"
imageAlt: "Implementar Evidência de Chaves Públicas no Kubernetes"
imageAuthor: "Growtika"
imageSource: ""
---

## Visão geral  

Em ambientes Kubernetes, a autenticação entre *workloads* costuma depender de tokens ou certificados gerados por uma CA (Autoridade Certificadora) interna. Porém, esses mecanismos não garantem que o *pod* realmente possua a chave privada correspondente à chave pública reconhecida pelo cluster. A técnica de *evidência de chaves públicas* (*public key proof*) permite que o *workload* comprove a posse da chave privada, aumentando a confiança nas comunicações internas e externas.  

## Como funciona  

1. **Geração do par de chaves** – Cada *pod* cria localmente um par de chaves RSA ou ECDSA.  
2. **Registro da chave pública** – O *pod* publica sua chave pública em um `ConfigMap` ou em um `Secret` de leitura pública.  
3. **Prova de posse** – Ao se comunicar com outro *pod*, o emissor assina um desafio enviado pelo destino.  
4. **Validação** – O *pod* receptor verifica a assinatura usando a chave pública armazenada em seu *cache*.  

Essa abordagem elimina a necessidade de distribuir certificados de cliente, pois a posse da chave privada é comprovada em tempo real.  

## Implementação passo a passo  

### 1. Gerar o par de chaves no pod  

```bash
openssl genpkey -algorithm RSA -out private.pem -pkeyopt rsa_keygen_bits:2048  
openssl rsa -pubout -in private.pem -out public.pem  
```  

Os comandos acima geram a chave privada (`private.pem`) e a chave pública (`public.pem`).  

### 2. Armazenar a chave pública no Kubernetes  

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pod-public-keys
  namespace: default
data:
  pod-1: |
    -----BEGIN PUBLIC KEY-----
    MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAn...
    -----END PUBLIC KEY-----
```

O `ConfigMap` pode ser criado com o comando `kubectl apply -f`.  

### 3. Implementar o desafio/assinatura  

O *pod* receptor expõe um *endpoint* `/challenge` que retorna um *token* aleatório.  
O *pod* emissor obtém o *token*, assina-o com sua chave privada e o envia de volta.  

```go
// Pseudo-código em Go
token, _ := http.Get("http://pod-receptor/challenge")
sig, _ := rsa.SignPKCS1v15(rand.Reader, privateKey, crypto.SHA256, token)
http.Post("http://pod-receptor/verify", sig)
```

Ao receber a assinatura, o receptor a valida utilizando a chave pública registrada no `ConfigMap`.  

### 4. Automatizar com cert-manager e Webhook  

Para evitar o gerenciamento manual, utilize o cert-manager para emitir certificados de cliente e um *webhook* de *admission* para inserir a chave pública no `ConfigMap` automaticamente.  

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: pod-1-cert
spec:
  secretName: pod-1-tls
  dnsNames:
    - pod-1.default.svc.cluster.local
  issuerRef:
    name: selfsigned-issuer
    kind: Issuer
```

O *webhook* pode monitorar a criação do `Secret` `pod-1-tls` e extrair a chave pública para o `ConfigMap`.  

## Benefícios práticos  

- **Confiança reforçada** – A posse da chave privada é comprovada em cada interação.  
- **Menor dependência de CA** – Reduz a complexidade do gerenciamento de certificados.  
- **Escalabilidade** – A lógica de desafio/assinatura pode ser centralizada em um *sidecar* ou serviço de controle.  

## Conclusão prática  

Para adotar a evidência de chaves públicas em seu cluster Kubernetes, comece gerando pares de chaves em cada *pod*, registre as chaves públicas em um `ConfigMap` e implemente um protocolo simples de desafio/assinatura. Utilize o cert-manager e um *webhook* para automatizar a sincronização das chaves. Dessa forma, você garante que apenas *workloads* legítimos, que realmente detêm a chave privada, possam estabelecer comunicações seguras, elevando o nível de segurança do seu ambiente.
