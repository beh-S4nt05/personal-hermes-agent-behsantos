---
name: arquitetura-mvvm
description: "Arquitetura MVVM (Model-View-ViewModel): separação de apresentação, data binding, testabilidade. Use quando a tarefa envolver mvvm, model view viewmodel, viewmodel, data binding, observable, wpf, xamarin ou android mvvm."
---
# MVVM — Model · View · ViewModel

## O mapa (o que é cada coisa)
- **Model**: dados + regra de negócio (não sabe que a UI existe).
- **View**: tela burra — renderiza estado, dispara eventos.
- **ViewModel**: expõe **estado observável** + comandos; orquestra
  Models; **nunca referencia a View**.

## Fluxo (unidirecional na prática)
View (evento) → ViewModel (método) → Model (regra/dados) →
ViewModel atualiza estado observável → View re-renderiza (binding).

## Por ecossistema
- **Android**: ViewModel + StateFlow + Compose (ou DataBinding XML).
- **WPF**: INotifyPropertyChanged + CommunityToolkit.Mvvm.
- **Vue**: `ref/reactive` do Vue É o ViewModel (`computed` = derivado).

## Regras de sênior
- Estado no ViewModel é **únICA fonte de verdade** — View não guarda estado duplicado.
- ViewModel sem `import` de UI (testável sem emulador).
- Mapear Model→ViewModel (nunca expor entity direto na tela).

## Armadilhas
- Lógica de negócio na View (receita de bug).
- Observable aninhado demais (uso `flatMapLatest`/`switchMap`).
- ViewModel dependendo do contexto de Activity (vaza memória).

## Verificação
Teste unitário do ViewModel SEM UI · cada camada em pasta própria.
